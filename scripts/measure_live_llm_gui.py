#!/usr/bin/env python3
"""Opt-in, billed GUI measurements; never imported or run by pytest/CI.

Use --paid to authorize requests. Read credentials in memory from --env-file;
write only timing, action, usage, and game-result metadata to --output.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from threading import Event, get_ident
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def stats(values):
    ordered = sorted(values)
    if not ordered:
        return {"samples": 0}
    return {"samples": len(ordered), "median_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * .95))], 3),
            "max_ms": round(max(ordered), 3),
            "over_100ms": sum(value > 100 for value in ordered)}


class Meter:
    def __init__(self, client, limit):
        self.client = client
        self.limit = limit
        self.records = []
        self.started = Event()
        self.scenario = ""
        self.main_thread = get_ident()

    def chat(self, messages, model, max_tokens):
        if len(self.records) >= self.limit:
            raise RuntimeError("Manual measurement request cap reached")
        entry = {"request": len(self.records) + 1, "scenario": self.scenario,
                 "main_thread": get_ident() == self.main_thread, "model": model,
                 "max_tokens": max_tokens}
        self.records.append(entry)
        self.started.set()
        begin = time.perf_counter()
        try:
            result = self.client.chat(messages, model, max_tokens)
            entry.update(status=result["status"], usage=result.get("usage"),
                         finish_reason=result.get("finish_reason"))
            try:
                from chaos_blackjack.ai.pipeline import _strip_json_fence
                action = json.loads(_strip_json_fence(result["answer"]))
                entry["action"] = {key: action[key] for key in ("action", "rule_id", "item_id")
                                   if isinstance(action, dict) and key in action}
            except (ValueError, TypeError):
                entry["invalid_json"] = True
            return result
        except Exception as exc:
            entry["error"] = self.client.redact(str(exc))[:500]
            raise
        finally:
            entry["duration_s"] = round(time.perf_counter() - begin, 4)
            print(json.dumps({"request_finished": entry}, ensure_ascii=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paid", action="store_true", help="explicitly opt into billed API calls")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--max-requests", type=int, default=16)
    args = parser.parse_args()
    if not args.paid or not 1 <= args.rounds <= 20 or not 1 <= args.max_requests <= 40:
        parser.error("--paid is required; rounds must be 1..20 and max-requests 1..40")
    if os.environ.get("CI", "").lower() in ("1", "true"):
        parser.error("Billed measurements are disabled in CI")

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ["CHAOS_USE_LLM"] = "0"  # Only the explicitly injected real backend may call out.
    import pygame
    from chaos_blackjack.ai.env import load_dotenv_from_project_root
    from chaos_blackjack.ai.gptsapi_llm import create_client_from_env, GptsApiLLM, DEFAULT_MODEL
    from chaos_blackjack.ai.pipeline import ChaosPipeline
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.view import TablePhase, Action
    from chaos_blackjack.core.game_loop import GameLoop
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.scenes.table import ACTION_Y, W
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    load_dotenv_from_project_root(args.env_file)
    client = create_client_from_env()
    model = os.environ.get("GPTSAPI_MODEL", "").strip() or DEFAULT_MODEL
    meter = Meter(client, args.max_requests)
    # Use the configured model, bounding output tokens for this measurement only.
    max_tokens = min(256, int(os.environ.get("GPTSAPI_MAX_TOKENS", "256") or 256))
    backend = GptsApiLLM(meter, model=model, max_tokens=max_tokens)
    report = {"started_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "tested_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                       text=True).strip(),
              "python": platform.python_version(), "pygame": pygame.version.ver,
              "platform": platform.platform(), "video_driver": "dummy",
              "target_fps": 60, "model": model, "base_url": client.base_url,
              "timeout_s": client.timeout, "max_tokens": max_tokens,
              "request_cap": args.max_requests, "scenarios": [], "requests": meter.records}
    app = App(GuiSettings())
    app.running = True
    clock = pygame.time.Clock()
    notices = []

    def open_table(seed):
        pipeline = ChaosPipeline.from_profile_name("easy", "chaotic", backend)
        ctrl = GameController(RunConfig(enable_chaos=True, seed=seed, target_money=10000),
                              loop_factory=lambda d: GameLoop(dispatcher=d, pipeline=pipeline))
        app.scenes.reset("table", controller=ctrl)
        app.scenes.apply_pending()
        table = app.scenes.top
        table.subscribe("*", lambda n: notices.append(
            {"kind": n.kind, "main_thread": get_ident() == meter.main_thread}))
        return table

    def key(keycode):
        start = time.perf_counter()
        app._dispatch(pygame.event.Event(pygame.KEYDOWN, key=keycode, mod=0, unicode=""))
        app.scenes.apply_pending()
        return (time.perf_counter() - start) * 1000

    def frame(metrics=None):
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            app._dispatch(event)
        start = time.perf_counter()
        app.scenes.update(dt)
        app.scenes.apply_pending()
        update_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        app._render()
        render_ms = (time.perf_counter() - start) * 1000
        if metrics is not None:
            metrics["update"].append(update_ms)
            metrics["render"].append(render_ms)
            metrics["interval"].append(dt * 1000)
            metrics["animation"].add(tuple(tuple(app.canvas.get_at(
                (W // 2 + (i - 1) * 18, ACTION_Y + 42))) for i in range(3)))

    def pump_until(predicate, *, timeout=100, metrics=None):
        deadline = time.perf_counter() + timeout
        while not predicate():
            if time.perf_counter() > deadline:
                raise RuntimeError("GUI scenario deadline exceeded")
            frame(metrics)

    def begin(label, table):
        if len(meter.records) >= meter.limit:
            raise RuntimeError("Request cap reached before the next scenario")
        meter.scenario = label
        meter.started.clear()
        table._deal(5)
        pump_until(lambda: meter.started.is_set())
        assert table._chaos_future is not None
        return table._chaos_future

    def finish_round(table):
        decisions = []
        while table.view.phase == TablePhase.PLAYER_TURN:
            view = table.view
            method = "hit" if view.player_total < 17 and view.can(Action.HIT) else "stand"
            if len(decisions) >= 20:
                raise RuntimeError("Player action guard reached")
            decisions.append(method)
            table._command(method)()
            frame()
        pump_until(lambda: table.view.phase in (TablePhase.ROUND_OVER, TablePhase.RUN_OVER))
        return decisions, asdict(table.view.last_result)

    try:
        table = open_table(7)
        for _ in range(30):
            frame()  # Warm font and asset caches before the measurements.
        meter.scenario = "synchronous_control"
        table._deal(5)
        start = time.perf_counter()
        # Reproduce the previous table implementation's blocking command.
        table._command("resolve_chaos")()
        blocked_ms = (time.perf_counter() - start) * 1000
        decisions, result = finish_round(table)
        report["scenarios"].append({"name": meter.scenario, "blocked_main_thread_ms": round(blocked_ms, 3),
                                    "llm_error": backend.last_error, "decisions": decisions, "result": result})

        table = open_table(7)
        for number in range(1, args.rounds + 1):
            if table.view.phase == TablePhase.ROUND_OVER:
                table._command("next_round")()
            label = f"async_round_{number}"
            offset = len(meter.records)
            future = begin(label, table)
            cached = table.view
            metrics = {"update": [], "render": [], "interval": [], "animation": set()}
            controls_ms = [key(code) for code in (pygame.K_h, pygame.K_s, pygame.K_d,
                                                pygame.K_r, pygame.K_RETURN)]
            assert table.view is cached
            assert all(not button.enabled for button in table.action_buttons.values())
            frame(metrics)
            modal_ms = None
            if number == 3 and not future.done():
                modal_ms = [key(pygame.K_ESCAPE)]
                assert type(app.scenes.top).__name__ == "ConfirmScene"
                for _ in range(5):
                    frame()
                modal_ms.append(key(pygame.K_ESCAPE))
                assert app.scenes.top is table
            pump_until(lambda: table._chaos_future is None, metrics=metrics)
            assert not table._chaos_failed
            assert all(not record["main_thread"] for record in meter.records[offset:])
            animation_states = len(metrics.pop("animation"))
            decisions, result = finish_round(table)
            row = {"name": label, "requests": len(meter.records) - offset,
                   "llm_error": backend.last_error, "update": stats(metrics["update"]),
                   "render": stats(metrics["render"]), "interval": stats(metrics["interval"]),
                   "animation_states": animation_states, "controls": stats(controls_ms),
                   "modal_open_close_ms": modal_ms,
                   "rules": [rule.id for rule in table.view.active_rules],
                   "decisions": decisions, "result": result}
            report["scenarios"].append(row)
            print(json.dumps({"scenario_finished": row}, ensure_ascii=True), flush=True)

        for label in ("return_to_menu_in_flight", "window_quit_in_flight"):
            table = open_table(11)
            future = begin(label, table)
            assert not future.done(), "Request finished before the exit probe"
            cached = table.view
            notice_offset = len(notices)
            if label.startswith("return"):
                open_ms = key(pygame.K_ESCAPE)
                exit_ms = key(pygame.K_RETURN)
                assert type(app.scenes.top).__name__ == "MainMenuScene"
                assert table._closed
                replacement = open_table(23)
                replacement_view = replacement.view
            else:
                open_ms = None
                start = time.perf_counter()
                app._dispatch(pygame.event.Event(pygame.QUIT))
                exit_ms = (time.perf_counter() - start) * 1000
                assert not app.running
                table.on_exit()
                replacement = None
            finished_at_exit = future.done()
            pump_until(future.done)
            future.result()
            assert table.view is cached
            assert len(notices) == notice_offset
            if replacement is not None:
                assert replacement.view is replacement_view
            report["scenarios"].append({"name": label, "dialog_open_ms": open_ms,
                "exit_ms": round(exit_ms, 3), "request_finished_at_exit": finished_at_exit,
                "late_result_ignored": True, "llm_error": backend.last_error})

        report["passed"] = all(not record.get("error") for record in meter.records)
        report["notice_callbacks_on_main_thread"] = all(n["main_thread"] for n in notices)
        report["rejected_chaos_actions"] = sum(n["kind"] == "chaos_action_rejected" for n in notices)
    except Exception as exc:
        report["passed"] = False
        report["harness_error"] = client.redact(f"{type(exc).__name__}: {exc}")[:1000]
    finally:
        pygame.quit()
        report["finished_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
        report["request_count"] = len(meter.records)
        report["usage_totals"] = {key: sum((r.get("usage") or {}).get(key, 0) or 0
                                          for r in meter.records)
                                  for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report.get("passed"), "request_count": report["request_count"],
                          "usage_totals": report["usage_totals"], "output": str(args.output),
                          "harness_error": report.get("harness_error")}, ensure_ascii=True), flush=True)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
