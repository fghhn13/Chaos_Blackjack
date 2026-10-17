"""J-54's public table snapshot: what any player at the table may see.

Built fresh by `J54Table.public()` (docs/design/J54_V2_SPEC.md section 8);
frozen and JSON-safe, so a view never changes the table and later changes
never reach an old view. It never holds undealt cards or the deck order: the
deck's make-up is public at this table, and the meter and the heat map are
the evaluator's reading of that make-up (chaos_blackjack/j54/evaluator.py).
Parts (parts.py) and the agent observation read only this.

The meter reads the deck the next round is dealt from (the run's deck, plus
the Joker once released) under the condition in force and the firmware. It
shows direction and advice, never a plan: `bar` is the win probability of one
hand, `band` the betting band it falls in with the suggested stake, `heat` the
change of the win probability (percentage points) when one card of a group
leaves the deck (positive = removing it helps the player).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from chaos_blackjack.j54.deck_ops import RANKS
from chaos_blackjack.j54.evaluator import Evaluator, HandStats, Valuation

if TYPE_CHECKING:
    from chaos_blackjack.j54.table import J54Table


@dataclass(frozen=True)
class J54Snapshot:
    compute: int
    compute_cap: int
    condition: dict[str, Any] | None          # {"id", "name", "text", "camp", "rounds_left"}
    announcement: str | None                  # "Next condition: anti camp.", or None
    program: tuple[dict[str, Any], ...] | None   # the whole schedule when announce == "schedule", else None
    firmware: dict[str, str] | None           # {"id", "name", "text"}
    joker: str                                # "sealed" | "in the deck" | "captured"
    deck_size: int                            # cards the next round is dealt from (the Joker included)
    removed: int                              # cards in the removed pile
    bounty: dict[str, Any] | None             # {"rank", "chips"}
    target: int
    target_from_round: int
    round: int
    rounds: int
    bar: float                                # win probability of one hand, 0..1
    ev: float                                 # expected result of one hand, in bets
    band: dict[str, int]                      # {"low": %, "stake_pct", "suggested": chips}
    capture: float                            # P(you draw the Joker in a hand); 0 unless it is in the deck
    heat: dict[str, float]                    # group ("5r", "Kb") -> pp; only groups present
    bands: tuple[dict[str, int], ...] = ()    # every band: {"low", "stake_pct"}, lowest first
    groups: dict[str, int] | None = None      # cards per group present
    removed_cards: tuple[str, ...] = ()       # the removed pile, oldest first ("5♥")
    seen: tuple[dict[str, Any], ...] = ()     # the conditions begun so far: {"id", "name", "camp", "start", "end"}
    kind: str = "j54"

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON data (lists, not tuples), detached from the snapshot."""
        return json.loads(json.dumps(asdict(self)))

    def rank_heat(self, rank: str) -> float:
        """Heat of a rank, summed over both colours (0 when none is left)."""
        return sum(self.heat.get(f"{rank}{c}", 0.0) for c in "rb")


# --------------------------------------------------------------------------- bands


def parse_bands(text: str) -> tuple[tuple[int, int], ...]:
    """`"50:10,55:20,60:30"` -> ((50, 10), (55, 20), (60, 30)): from `low` % up, stake `pct` % of the bankroll."""
    out = []
    for part in str(text).split(","):
        if part.strip():
            low, _, pct = part.partition(":")
            out.append((int(low), int(pct)))
    return tuple(sorted(out))


def band_for(bar: float, bands: tuple[tuple[int, int], ...], bankroll: int, bet_min: int,
             bet_max: int) -> dict[str, int]:
    """The band `bar` falls in and its suggested stake (the minimum below the first band), within the bet range."""
    low, pct = 0, 0
    for b_low, b_pct in bands:
        if bar * 100 >= b_low:
            low, pct = b_low, b_pct
    chips = bankroll * pct // 100 if pct else bet_min
    suggested = max(bet_min, min(bet_max, chips)) if bet_max >= bet_min else bet_min
    return {"low": low, "stake_pct": pct, "suggested": suggested}


# --------------------------------------------------------------------------- the evaluator


def valuation(table: "J54Table") -> Valuation:
    """The condition in force (J-54's rules or stand threshold), the firmware (the player's rules or
    bust line) and whether the Joker is in the deck."""
    m, fw = table.condition(), table.firmware
    return Valuation(
        dealer_rules=m.valuation() if m is not None else (),
        player_rules=tuple(dict(r) for r in fw.rules) if fw is not None else (),
        dealer_stand_on=m.threshold if m is not None and m.threshold is not None else 17,
        player_bust=fw.bust_limit(21) if fw is not None else 21,
        joker_in_deck=table.joker == "in the deck",
    )


def measure(table: "J54Table") -> tuple[HandStats, dict[str, float]]:
    """The meter and the heat map of the deck the next round is dealt from (the Joker is added by the
    valuation). Kept on the table until the deck or the valuation changes, i.e. once per betting phase
    and again after each table move."""
    v = valuation(table)
    key = (tuple(sorted((str(c.rank), c.suit) for c in table.cards)), v.key())
    cached = getattr(table, "_meter", None)
    if cached is not None and cached[0] == key:
        return cached[1], cached[2]
    ev = Evaluator(v)
    stats, heat = ev.stats(table.cards), dict(ev.heat(table.cards))
    table._meter = (key, stats, heat)  # noqa: SLF001 - the table owns the cache, this module fills it
    return stats, heat


def rank_heat(heat: dict[str, float]) -> dict[str, float]:
    """Heat per rank present, summed over both colours."""
    out: dict[str, float] = {}
    for group, pp in heat.items():
        out[group[:-1]] = out.get(group[:-1], 0.0) + pp
    return out


def hottest_ranks(heat: dict[str, float], n: int) -> list[str]:
    """The `n` ranks with the highest heat (both colours summed), ties by rank order."""
    per_rank = rank_heat(heat)
    return sorted(per_rank, key=lambda r: (-per_rank[r], RANKS.index(r)))[:n]


def heat_text(pp: float) -> str:
    """"+0.3 pp · cut" / "-0.2 pp · keep"."""
    return f"{pp:+.1f} pp · {'cut' if pp > 0 else 'keep'}"


# --------------------------------------------------------------------------- the snapshot


def snapshot(table: "J54Table") -> J54Snapshot:
    m = table.condition()
    condition = None if m is None else {"id": m.id, "name": m.name, "text": m.text, "camp": m.camp,
                                        "rounds_left": table.rounds_left()}
    segments = tuple({"id": s.rule, "name": table.conditions[s.rule].name, "camp": table.conditions[s.rule].camp,
                      "start": s.start, "end": s.end} for s in table.program.segments)
    program = segments if table.settings["announce"] == "schedule" else None
    fw = table.firmware
    stats, heat = measure(table)
    bands = parse_bands(table.settings["bands"])
    run = table.c.run
    lo, hi = table.c.bet_limits()
    groups = {g: n for g, n in table.group_counts().items() if n}
    return J54Snapshot(
        compute=table.compute, compute_cap=table.compute_cap, condition=condition,
        announcement=table.announcement, program=program,
        firmware={"id": fw.id, "name": fw.name, "text": fw.text} if fw else None, joker=table.joker,
        deck_size=table.deck_size, removed=len(table.removed),
        bounty={"rank": table.bounty_rank, "chips": table._int("bounty")} if table.bounty_rank else None,  # noqa: SLF001
        target=run.target_money, target_from_round=table._int("target_from_round"),  # noqa: SLF001
        round=table.entered_round, rounds=table.rounds,
        bar=round(stats.win, 4), ev=round(stats.ev, 4), band=band_for(stats.win, bands, run.money, lo, hi),
        capture=round(stats.capture, 4), heat={g: round(pp, 2) for g, pp in heat.items()},
        bands=tuple({"low": low, "stake_pct": pct} for low, pct in bands), groups=groups,
        removed_cards=tuple(f"{c.rank}{c.suit}" for c in table.removed),
        seen=segments[:table.segment + 1],
    )


__all__ = ["J54Snapshot", "band_for", "heat_text", "hottest_ranks", "measure", "parse_bands", "rank_heat",
           "snapshot", "valuation"]
