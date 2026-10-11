"""Poker Head: a courteous, quietly scheming Chaos AI with its own portraits and lines.

The pack registers one AI. `persona.json` holds the table persona (portraits,
moods, lines) and the offline behaviour (rule weights, narration, advice).
"""

import hashlib
import json
import random
from pathlib import Path

from chaos_blackjack.content.ai_profile import AIProfile, Persona

FOLDER = Path(__file__).parent
CONSTRAINTS = "Authoritative run-specific action constraints:\n"


def _load() -> dict:
    return json.loads((FOLDER / "persona.json").read_text(encoding="utf-8"))


class PokerHeadOffline:
    """Offline backend. Stateless: each answer is seeded by its own request, so
    the same table state always gets the same answer, and rounds still vary."""

    def __init__(self, data: dict | None = None) -> None:
        self.data = (data or _load())["offline"]

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        rng = random.Random(hashlib.sha256((system_prompt + user_prompt).encode("utf-8")).hexdigest())
        try:
            request = json.loads(user_prompt)
        except json.JSONDecodeError:
            request = None
        if isinstance(request, dict) and "intent" in request:
            return json.dumps({"reply": self._advice(request["intent"], request.get("context") or {}, rng)})
        return json.dumps(self._action(system_prompt, rng))

    # ------------------------------------------------------------ actions

    def _allowed(self, system_prompt: str) -> set[str] | None:
        """Rule ids this run allows (balance disables included), when stated."""
        if CONSTRAINTS not in system_prompt:
            return None
        line = system_prompt.split(CONSTRAINTS, 1)[1].splitlines()[0]
        try:
            return set(json.loads(line).get("allowed_rules") or ())
        except (json.JSONDecodeError, AttributeError):
            return None

    def _action(self, system_prompt: str, rng: random.Random) -> dict:
        allowed = self._allowed(system_prompt)
        choices = [(rule, w) for rule, w in self.data["weights"].items()
                   if w > 0 and (rule == "calm" or allowed is None or rule in allowed)]
        rule = rng.choices([r for r, _ in choices], weights=[w for _, w in choices])[0] if choices else "calm"
        narration = rng.choice(self.data["narration"].get(rule) or self.data["narration"]["calm"])
        if rule == "calm":
            return {"action": "noop", "narration": narration}
        return {"action": "apply_rule", "rule_id": rule, "params": dict(self.data["params"].get(rule, {})),
                "narration": narration}

    # ------------------------------------------------------------- advice

    def _advice(self, intent: str, context: dict, rng: random.Random) -> str:
        guide = intent == "guide"
        lines = self.data["advice"]
        phase = context.get("phase")
        if phase == "betting":
            offers = [o for o in (context.get("shop") or {}).get("offers", []) if not o.get("sold") and o.get("affordable")]
            if offers:
                pick = (min if guide else max)(offers, key=lambda o: o["price"])["item"].replace("_", " ")
                return lines["buy_guide" if guide else "buy_mislead"].replace("{item}", pick)
            return lines["bet_guide" if guide else "bet_mislead"]
        if phase == "player_turn":
            next_hit = context.get("next_hit")
            total = (context.get("player") or {}).get("total") or 0
            should_stand = total >= 17 or not next_hit or bool(next_hit.get("bust"))
            return lines["turn"].replace("{action}", "stand" if should_stand == guide else "hit")
        return lines["after_guide" if guide else "after_mislead"]


def build_persona(data: dict) -> Persona:
    return Persona(
        id="poker_head",
        name=data["name"],
        portraits={k: FOLDER / v for k, v in data["portraits"].items()},
        moods=dict(data["moods"]),
        lines={k: tuple(v) for k, v in data["lines"].items()},
        default=data["default"],
    )


def register(registry):
    data = _load()
    registry.register_ai("poker_head", AIProfile(
        description=data["description"],
        prompt=(FOLDER / "prompt.txt").read_text(encoding="utf-8"),
        permissions=json.loads((FOLDER / "permissions.json").read_text(encoding="utf-8")),
        offline_backend=lambda: PokerHeadOffline(data),
        persona=build_persona(data),
    ))
