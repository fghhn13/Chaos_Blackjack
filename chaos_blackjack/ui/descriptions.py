"""Human-readable chaos rules and modifiers for info / Chaos panel."""

from __future__ import annotations

from typing import Any

from chaos_blackjack.rules.modifiers import ActiveModifiers, merge_chaos_flags


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
        lines.append("Bust may not auto-lose for the player (while active).")
    return lines if lines else ["No numeric perturbations (baseline blackjack)."]


def _describe_one(tid: str, m: Any) -> str:
    if tid == "modify_card_value":
        d = getattr(m, "delta", None)
        if d is not None:
            return f"Rank values shifted by {d:+} per card (until cleared)."
        return "Rank values modified by active chaos rule."
    if tid == "reverse_bust":
        return "Reverse bust: high player totals may not count as bust for outcome."
    return f"Active rule: {tid}"


def info_rules_text(modifiers: ActiveModifiers) -> str:
    lines = ["Current Rules:"]
    lines.extend(f"- {x}" for x in describe_active_modifiers(modifiers))
    fl = merge_chaos_flags(modifiers.items)
    if fl:
        lines.append(f"- Flags: {', '.join(sorted(fl))}")
    return "\n".join(lines)
