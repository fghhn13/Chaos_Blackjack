"""Human-readable chaos rules and modifiers for info / Chaos panel."""

from __future__ import annotations

from typing import Any

from chaos_blackjack.rules.modifiers import ActiveModifiers, merge_chaos_flags


# Display names of the built-in rules (the codex, the run log and the GUI parts share them).
RULE_NAMES = {
    "modify_card_value": "Value Shift", "great_crash": "Great Crash",
    "odd_even_chaos": "Odd-Even Chaos", "suit_power": "Suit Power",
    "fragile_bust": "Fragile Bust", "reverse_bust": "Reverse Bust",
    "tiebreaker_shift": "Tiebreaker Shift",
}


def rule_display_name(rule_id: str) -> str:
    """A rule's player-facing name: built-in names, J-54's deck rules, else the id in title case."""
    if rule_id in RULE_NAMES:
        return RULE_NAMES[rule_id]
    from chaos_blackjack.rules.plugins.j54_deck import DECK_RULES

    if rule_id in DECK_RULES:
        return DECK_RULES[rule_id][0]
    return rule_id.replace("_", " ").title()


def chaos_ai_flavor(mod_count: int) -> str:
    if mod_count == 0:
        return "The table feels oddly quiet..."
    if mod_count == 1:
        return "You look too comfortable..."
    return "The rules shimmer — hold on tight."


def describe_active_modifiers(modifiers: ActiveModifiers) -> list[str]:
    lines: list[str] = []
    flags = modifiers.chaos_flags()
    for m in modifiers.items:
        tid = getattr(m, "id", "?")
        line = _describe_one(tid, m)
        if line:
            lines.append(line)
    if "reverse_bust" in flags and not any(
        "reverse" in x.lower() for x in lines
    ):
        lines.append("A player bust is a push this round.")
    return lines if lines else ["No numeric perturbations (baseline blackjack)."]


def _describe_one(tid: str, m: Any) -> str:
    if tid == "modify_card_value":
        d = getattr(m, "delta", None)
        if d is not None:
            return f"Rank values shifted by {d:+} per card (until cleared)."
        return "Rank values modified by active chaos rule."
    if tid == "reverse_bust":
        return "Reverse Bust: if you bust this round, it is a push instead of a loss."
    if tid == "great_crash":
        return f"The Great Crash: all 10/J/Q/K become value {getattr(m, 'ten_value', 1)} (until cleared)."
    if tid == "odd_even_chaos":
        even, odd = getattr(m, "even_delta", 2), getattr(m, "odd_delta", -1)
        return f"Odd-Even Chaos: 2/4/6/8 {even:+}, 3/5/7/9 {odd:+}; A/10/J/Q/K unchanged (until cleared)."
    if tid == "suit_power":
        red, black = getattr(m, "red_delta", 1), getattr(m, "black_delta", -1)
        return f"Suit Power: red suits {red:+}, black suits {black:+} (until cleared)."
    if tid == "fragile_bust":
        return f"Fragile Table: bust threshold reduced to {getattr(m, 'bust_limit', 18)} (instead of 21)."
    if tid == "tiebreaker_shift":
        flags = getattr(m, "chaos_flags", frozenset())
        if "dealer_wins_ties" in flags:
            return "Tiebreaker Shift: ties go to Dealer (instead of Push)."
        return "Tiebreaker Shift: ties go to Player (instead of Push)."
    if getattr(m, "deck_rule", False):  # J-54's deck operations describe themselves
        return m.describe()
    return f"Active rule: {tid}"


def describe_modifier(m: Any) -> str:
    return _describe_one(getattr(m, "id", "?"), m)


def info_rules_text(modifiers: ActiveModifiers) -> str:
    lines = ["Current Rules:"]
    lines.extend(f"- {x}" for x in describe_active_modifiers(modifiers))
    fl = merge_chaos_flags(modifiers.items)
    if fl:
        lines.append(f"- Flags: {', '.join(sorted(fl))}")
    return "\n".join(lines)
