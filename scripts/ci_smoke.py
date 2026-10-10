"""Exercise the assembled application and packaged resources without billing.

Use --installed outside the checkout to check a wheel, and --gui to render
the player hub and its real codex handoff with SDL's dummy drivers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import sysconfig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.installed:
        sys.path.insert(0, str(root))
    os.environ["CHAOS_USE_LLM"] = "0"
    os.environ["CHAOS_DB"] = ":memory:"
    os.environ.pop("CHAOS_PROFILE", None)
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

    import chaos_blackjack
    from chaos_blackjack import meta
    from chaos_blackjack.agent import AgentSession
    from chaos_blackjack.ai.permissions_loader import load_permission_profile
    from chaos_blackjack.ai.prompts_loader import load_prompt
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.view import TablePhase
    from chaos_blackjack.audio.catalog import validate_assets
    from chaos_blackjack.codex import codex_entries, run_demo
    from chaos_blackjack.data import connect

    if args.installed:
        source = Path(chaos_blackjack.__file__).resolve()
        installed = Path(sysconfig.get_path("purelib")).resolve() / "chaos_blackjack"
        assert source.parent == installed, f"Imported the checkout instead of the wheel: {source}"
    assert load_permission_profile("easy")
    assert load_prompt("chaotic")
    assert validate_assets()["ok"]
    agent = AgentSession.new(seed=7, chaos=True)
    assert agent.execute({"cmd": "bet", "amount": 10})["ok"]
    assert AgentSession.from_state(agent.to_state()).observe() == agent.observe()

    db = connect(":memory:")
    service = meta.MetaService(db)
    meta.use_service(service)
    try:
        player = meta.create_player(1, "CI player")
        service.grant_tokens(player.id, 100)
        player = meta.buy_upgrade(player.id, "start_money")
        assert player.upgrades["start_money"] == 1
        started = meta.start_run(player.id, "normal", seed=7)
        controller = started.controller
        controller.save("ci-checkpoint")
        restored = meta.resume_run(player.id)
        assert restored is not None and restored.config == started.config
        assert restored.controller.view() == controller.view()
        controller = restored.controller
        for _ in range(2000):
            if controller.phase == TablePhase.RUN_OVER:
                break
            if controller.phase == TablePhase.BETTING:
                controller.place_bet(controller.view().bet_max)
            if controller.phase == TablePhase.CHAOS:
                controller.resolve_chaos()
            if controller.phase == TablePhase.PLAYER_TURN:
                controller.stand()
            controller.finish_dealer()
            if controller.phase == TablePhase.ROUND_OVER:
                controller.next_round()
        assert controller.phase == TablePhase.RUN_OVER
        reward = meta.finish_run(started.run_id, controller)
        assert reward.tokens == sum(value for _, value in reward.breakdown)
        assert meta.history(player.id)[0].result == reward.result
        assert meta.resume_run(player.id) is None
        config = RunConfig(use_llm=False)
        entries = codex_entries(config=config)
        demos = [run_demo(entry.demo, config) for entry in entries if entry.demo is not None]
        assert demos and all(demos)
        if args.gui:
            gui_smoke(player.id, config)
        print(json.dumps({"ok": True, "installed": args.installed, "gui": args.gui,
                          "run_result": reward.result, "codex_entries": len(entries), "demos": len(demos)}))
    finally:
        meta.use_service(None)
        db.close()


def gui_smoke(player_id: int, config) -> None:
    import pygame
    from chaos_blackjack.gui.app import App
    import chaos_blackjack.gui.scenes  # noqa: F401

    app = App(run_config=config)
    try:
        for name, params in (("menu", {}), ("player_select", {}),
                             ("meta_shop", {"player_id": player_id}),
                             ("history", {"player_id": player_id}),
                             ("hub", {"player_id": player_id})):
            app.scenes.reset(name, **params)
            app.scenes.apply_pending()
            app.scenes.draw(app.canvas)
        hub = app.scenes.top
        assert hub.nav["codex"].enabled
        hub.navigate("codex", player_id=player_id, config=config)
        app.scenes.apply_pending()
        gallery = app.scenes.top
        assert gallery.config == config and gallery.entries
        app.scenes.draw(app.canvas)
        app.scenes.push("codex_detail", entry=gallery.entries[0], config=config)
        app.scenes.apply_pending()
        app.scenes.update(0.1)
        app.scenes.draw(app.canvas)
        app.scenes.pop()
        app.scenes.apply_pending()
        app.scenes.pop()
        app.scenes.apply_pending()
        assert app.scenes.top is hub
        app.scenes.draw(app.canvas)
    finally:
        app.audio.close()
        pygame.quit()


if __name__ == "__main__":
    main()
