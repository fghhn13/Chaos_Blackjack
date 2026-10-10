"""`python -m chaos_blackjack.gui [--fullscreen] [--scene NAME] [--profile NAME]`"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Chaos Blackjack GUI")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--scene", default="menu", help="scene to open first (e.g. gallery)")
    p.add_argument("--profile", default=None, help="balance profile in data/game.db (default: $CHAOS_PROFILE or 'default')")
    args = p.parse_args(argv)

    from chaos_blackjack.ai.env import load_dotenv_from_project_root

    load_dotenv_from_project_root()
    from chaos_blackjack.data.balance import BalanceError
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings

    try:
        app = App(GuiSettings(fullscreen=args.fullscreen, balance_profile=args.profile))
    except BalanceError as e:
        raise SystemExit(f"Balance profile error: {e}") from None
    app.run(args.scene)


if __name__ == "__main__":
    main()
