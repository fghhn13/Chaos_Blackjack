#!/usr/bin/env python3
"""One opt-in billed round with memory, portrait replies and disk save/load.

Never run from pytest or CI. Credentials are read in memory from --env-file;
the report contains game history, replies, usage and timings, never credentials.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from measure_live_llm_gui import Meter, stats


class MemoryMeter(Meter):
    def __init__(self, client, limit, replayed_record=None):
        super().__init__(client, limit)
        self.replayed_record = replayed_record

    def chat(self, messages, model, max_tokens):
        user = messages[-1]["content"]
        if user.startswith("Full private game context:\n"):
            context = json.loads(user.split("\n")[1])
            intent = None
        else:
            payload = json.loads(user)
            context, intent = payload["context"], payload["intent"]
        offset = len(self.records)
        if self.replayed_record is not None and offset == 0:
            record = self.replayed_record
            assert self.scenario == "shop_poke_before_round" and record["status"] == 200
            assert record["model"] == model and record["intent"] == intent
            for field in ("memory", "bankroll", "shop", "inventory"):
                assert context[field] == record[field], "Recorded API reply belongs to a different test context"
            entry = dict(record)
            entry.update(reused_paid_response=True, original_duration_s=record["duration_s"], duration_s=0)
            self.records.append(entry)
            result = {"answer": record["response_text"]}
        else:
            result = super().chat(messages, model, max_tokens)
        self.records[offset].update(
            intent=intent, memory=context.get("memory"),
            context_phase=context["phase"], bankroll=context["bankroll"],
            shop=context["shop"], inventory=context["inventory"],
            response_text=self.client.redact(result["answer"])[:1000],
        )
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paid", action="store_true")
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-requests", type=int, default=4)
    parser.add_argument("--replay-initial-response", type=Path,
                        help="reuse a recorded paid response for the identical initial test context")
    args = parser.parse_args()
    if not args.paid:
        parser.error("--paid is required to authorize billed calls")
    if not 1 <= args.max_requests <= 4:
        parser.error("--max-requests must be 1..4")
    if os.environ.get("CI", "").lower() in ("1", "true"):
        parser.error("Billed measurements are disabled in CI")

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ["CHAOS_USE_LLM"] = "0"  # Only the explicitly injected backend can call out.
    import pygame
    from chaos_blackjack.ai.env import load_dotenv_from_project_root
    from chaos_blackjack.ai.gptsapi_llm import create_client_from_env, GptsApiLLM, DEFAULT_MODEL
    from chaos_blackjack.ai.pipeline import ChaosPipeline
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.notices import NoticeKind
    from chaos_blackjack.app.view import TablePhase
    from chaos_blackjack.core.game_loop import GameLoop
    from chaos_blackjack.core.run_state import RunSaveData
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    load_dotenv_from_project_root(args.env_file)
    client = create_client_from_env()
    model = os.environ.get("GPTSAPI_MODEL", "").strip() or DEFAULT_MODEL
    previous = None
    if args.replay_initial_response:
        previous = json.loads(args.replay_initial_response.read_text("utf-8"))["requests"][0]
    meter = MemoryMeter(client, args.max_requests, previous)
    backend = GptsApiLLM(meter, model=model, max_tokens=256)
    config = RunConfig(enable_chaos=True, chaos_memory_enabled=True, seed=7, target_money=10000)
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "tested_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                       text=True).strip(),
              "model": model, "base_url": client.base_url, "timeout_s": client.timeout,
              "video_driver": "dummy", "memory_enabled": True, "memory_limit": 32,
              "seed": 7, "rounds": 1, "request_cap": args.max_requests, "max_tokens": 256,
              "requests": meter.records, "interactions": [], "checks": {}}
    scratch = ROOT / ".agent_runs" / "live-memory"
    scratch.mkdir(parents=True, exist_ok=True)

    def loop_factory(dispatcher):
        pipeline = ChaosPipeline.from_profile_name("easy", "chaotic", backend)
        # Exercise the real Chaos call in this one test round, even if its scheduler
        # would otherwise skip it. Its budget and action permission checks remain.
        pipeline.scheduler.should_attempt = lambda obs: True
        return GameLoop(dispatcher=dispatcher, pipeline=pipeline)

    def write_save(data, name):
        path = scratch / f"{name}.json"
        path.write_text(json.dumps(data.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")
        return path

    app = App(GuiSettings())
    clock = pygame.time.Clock()
    timing = {"update": [], "render": [], "interval": []}

    def frame():
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            app._dispatch(event)
        start = time.perf_counter()
        app.scenes.update(dt)
        app.scenes.apply_pending()
        timing["update"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        app._render()
        timing["render"].append((time.perf_counter() - start) * 1000)
        timing["interval"].append(dt * 1000)

    def pump_until(predicate):
        deadline = time.perf_counter() + client.timeout * 2 + 10
        while not predicate():
            if time.perf_counter() > deadline:
                raise RuntimeError("Live memory scenario deadline exceeded")
            frame()

    def key(code):
        app._dispatch(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=""))
        app.scenes.apply_pending()

    def open_table(controller):
        app.scenes.reset("table", controller=controller)
        app.scenes.apply_pending()
        return app.scenes.top

    def roundtrip(controller, name):
        expected = controller.chaos_memory.export()
        controller.save(name)
        data = RunSaveData.from_dict(json.loads((scratch / f"{name}.json").read_text("utf-8")))
        loaded = GameController.from_save(data, config, loop_factory=loop_factory, save_fn=write_save)
        assert loaded.chaos_memory.export() == expected, "Memory changed across disk save/load"
        return loaded

    def poke(table, label):
        meter.scenario = label
        offset = len(meter.records)
        click = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                   pos=table.chaos_panel.portrait_rect.center)
        for _ in range(8):
            app._dispatch(click)
        app.scenes.apply_pending()
        banner = app.scenes.top
        assert type(banner).__name__ == "ChaosPokeScene"
        frame_count = len(timing["interval"])
        animations = set()
        deadline = time.perf_counter() + client.timeout + 10
        while banner.reply is None:
            if time.perf_counter() > deadline:
                raise RuntimeError("Portrait request deadline exceeded")
            frame()
            animations.add(tuple(tuple(app.canvas.get_at(
                (banner.box.centerx + (i - 1) * 18, banner.box.centery + 20))) for i in range(3)))
        assert len(meter.records) == offset + 1, "Repeated clicks created extra paid requests"
        assert banner.reply.ok, "Real model did not return a valid text-only reply"
        reply, intent = banner.reply.text, banner.request.intent
        key(pygame.K_RETURN)
        assert any(entry["kind"] == NoticeKind.CHAOS_POKE_REPLY
                   and entry["details"]["text"] == reply for entry in table.controller.chaos_memory.export())
        report["interactions"].append({"scenario": label, "reply": client.redact(reply),
                                       "intent": intent,
                                       "rendered_frames": len(timing["interval"]) - frame_count,
                                       "animation_states": len(animations),
                                       "single_request_after_eight_clicks": True})
        print(json.dumps({"interaction_finished": label, "intent": intent,
                          "rendered_frames": len(timing["interval"]) - frame_count}), flush=True)
        return reply

    try:
        c = GameController(config, loop_factory=loop_factory, save_fn=write_save)
        table = open_table(c)
        for _ in range(10):
            frame()
        key(pygame.K_b)
        key(pygame.K_1)
        assert len(c.run.items) == 1
        report["purchased_item"] = c.run.items[0]
        first_reply = poke(table, "shop_poke_before_round")
        key(pygame.K_ESCAPE)  # close shop
        c = roundtrip(c, "before-round")
        report["checks"]["memory_survives_pre_round_disk_reload"] = True
        table = open_table(c)
        meter.scenario = "memory_enabled_chaos_turn"
        table._deal(5)
        pump_until(lambda: table.view.phase != TablePhase.CHAOS)
        assert not table._chaos_failed and backend.last_error is None
        report["decisions"] = []
        while table.view.phase == TablePhase.PLAYER_TURN:
            action = "hit" if table.view.player_total < 17 else "stand"
            report["decisions"].append(action)
            assert len(report["decisions"]) <= 20
            table._command(action)()
        pump_until(lambda: table.view.phase in (TablePhase.ROUND_OVER, TablePhase.RUN_OVER))
        assert table.view.phase == TablePhase.ROUND_OVER
        report["result"] = asdict(table.view.last_result)
        poke(table, "poke_after_round_result")
        for record in meter.records[1:]:
            assert any(entry["kind"] == NoticeKind.CHAOS_POKE_REPLY
                       and entry["details"]["text"] == first_reply for entry in record["memory"]), \
                "Previous reply missing from the actual later API payload"
        report["checks"]["previous_reply_sent_to_later_api_calls"] = True
        report["checks"]["shop_purchase_sent_to_all_api_calls"] = all(
            any(e["kind"] == NoticeKind.ITEM_BOUGHT for e in record["memory"]) for record in meter.records)
        report["checks"]["round_result_sent_to_final_poke"] = any(
            e["kind"] == NoticeKind.ROUND_SETTLED for e in meter.records[-1]["memory"])
        loaded = roundtrip(c, "after-round")
        report["checks"]["memory_survives_post_round_disk_reload"] = True
        report["final_memory"] = loaded.chaos_memory.export()
        report["checks"]["requests_run_off_main_thread"] = all(not r["main_thread"] for r in meter.records)
        report["passed"] = all(report["checks"].values()) and all(r.get("status") == 200 for r in meter.records)
    except Exception as exc:
        report["passed"] = False
        report["error"] = client.redact(f"{type(exc).__name__}: {exc}")[:1000]
    finally:
        pygame.quit()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["request_count"] = len(meter.records)
        report["new_billed_requests"] = sum(not r.get("reused_paid_response", False) for r in meter.records)
        report["timing_ms"] = {name: stats(values) for name, values in timing.items()}
        report["usage_totals"] = {name: sum((r.get("usage") or {}).get(name, 0) or 0 for r in meter.records)
                                  for name in ("prompt_tokens", "completion_tokens", "total_tokens")}
        text = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
        if os.environ["GPTSAPI_API_KEY"] in text:
            raise RuntimeError("Refusing to write report containing a credential")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({"passed": report.get("passed"), "requests": report["request_count"],
                          "usage": report["usage_totals"], "error": report.get("error"),
                          "output": str(args.output)}), flush=True)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
