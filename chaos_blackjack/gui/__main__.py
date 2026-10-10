"""`python -m chaos_blackjack.gui [--fullscreen] [--scene NAME]`"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Chaos Blackjack GUI")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--scene", default="menu", help="scene to open first (e.g. gallery)")
    args = p.parse_args(argv)

    from chaos_blackjack.ai.env import load_dotenv_from_project_root

    load_dotenv_from_project_root()
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings

    App(GuiSettings(fullscreen=args.fullscreen)).run(args.scene)


if __name__ == "__main__":
    main()
