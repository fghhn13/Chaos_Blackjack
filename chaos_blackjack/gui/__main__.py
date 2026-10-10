"""`python -m chaos_blackjack.gui [--fullscreen] [--scene NAME]`"""

from __future__ import annotations

import argparse

from chaos_blackjack.audio.catalog import DEFAULT_MASTER_VOLUME, checked_volume


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Chaos Blackjack GUI")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--volume", type=checked_volume, default=DEFAULT_MASTER_VOLUME, help="master volume, 0..1 (default 0.4)")
    p.add_argument("--mute", action="store_true", help="start with sound muted")
    p.add_argument("--scene", default="menu", help="scene to open first (e.g. gallery)")
    p.add_argument("--pack", action="append", default=[])
    p.add_argument("--ai", default="default")
    p.add_argument("--chaos", action="store_true")
    p.add_argument("--llm", action="store_true", default=None, help="explicitly use a billed real model")
    args = p.parse_args(argv)

    from chaos_blackjack.ai.env import load_dotenv_from_project_root

    load_dotenv_from_project_root()
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings

    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.content.loader import load_content_packs

    config = RunConfig(content_packs=tuple(args.pack), ai_id=args.ai,
                       enable_chaos=args.chaos or args.ai != "default", use_llm=args.llm)
    # Check pack selection before opening a window.
    catalog = load_content_packs(config.content_packs)
    if config.ai_id not in catalog.registry.ai_ids():
        p.error(f"Unknown AI id: {config.ai_id}")
    App(GuiSettings(fullscreen=args.fullscreen, master_volume=args.volume,
                    audio_muted=args.mute), run_config=config).run(args.scene)


if __name__ == "__main__":
    main()
