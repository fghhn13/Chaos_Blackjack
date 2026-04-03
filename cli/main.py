"""CLI entry — thin wrapper over `chaos_blackjack`."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python cli/main.py` without editable install
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chaos_blackjack.core.game_loop import GameLoop


def main() -> None:
    loop = GameLoop()
    state = loop.new_round(seed=42)
    final = loop.run_round_until_done(state)
    pv = loop.rules.hand_value(final.player_hand, loop.context())
    dv = loop.rules.hand_value(final.dealer_hand, loop.context())
    print("Chaos Blackjack (demo round)")
    print(f"  Player: { [c.rank for c in final.player_hand] } = {pv}")
    print(f"  Dealer: { [c.rank for c in final.dealer_hand] } = {dv}")
    print(f"  Outcome: {loop.outcome_label(final)}")


if __name__ == "__main__":
    main()
