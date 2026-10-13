"""AgentSession — play a run as an agent through plain command dicts.

    s = AgentSession.new(seed=7)
    s.execute({"cmd": "bet", "amount": 20})
    s.execute({"cmd": "act", "action": "hit"})

Every call returns {"ok": bool, "events": [...], "obs": {...}} and, on
failure, an "error" {code, message}. Phases the agent cannot influence
(chaos resolution, dealer drawing, moving to the next round) are advanced
automatically, so the agent only sees decision points: betting,
player_turn, run_over.

`to_state()` / `from_state()` make every step resumable from a file, which
is how one-shot shell commands keep a run going.
"""

from __future__ import annotations

import base64
import json
import random
import zlib
from typing import Any

from chaos_blackjack.agent.observation import build_observation, card_str, event_texts, round_result_dict
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.data.balance import load_balance
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.persistence import build_save_data
from chaos_blackjack.app.view import Action, TablePhase
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.logic.run_end_policy import RunEndResult

STATE_VERSION = 1
DEFAULT_MAX_STEPS = 2000
# Safety valve for auto-advance (dealer draws are bounded by the deck anyway).
_MAX_AUTO_STEPS = 200

# act <action> -> controller method
_ACT_METHODS = {
    Action.HIT: "hit",
    Action.STAND: "stand",
    Action.DOUBLE: "double_down",
    Action.SURRENDER: "surrender",
}

COMMANDS = {
    "observe": "Return the current observation (no state change).",
    "buy": "Buy a shop item while betting: {\"cmd\":\"buy\",\"item\":\"peek\"}",
    "reroll": "Roll the shop's stock again while betting (once per stock): {\"cmd\":\"reroll\"}",
    "bet": "Place a bet: {\"cmd\":\"bet\",\"amount\":20}",
    "act": "Act in your turn: {\"cmd\":\"act\",\"action\":\"hit|stand|double|surrender|use_item\",\"item\":\"peek\"}",
    "help": "List commands.",
}


class LlmUnavailable(RuntimeError):
    pass


class AgentSession:
    def __init__(
        self,
        controller: GameController,
        *,
        seed: int | None,
        use_llm: bool = False,
        max_steps: int = DEFAULT_MAX_STEPS,
        steps: int = 0,
        last_round: dict[str, Any] | None = None,
    ) -> None:
        self.controller = controller
        self.seed = seed
        self.use_llm = use_llm
        self.max_steps = max_steps
        self.steps = steps
        self.last_round = last_round

    # ------------------------------------------------------------- create

    @classmethod
    def new(
        cls,
        *,
        seed: int | None = None,
        chaos: bool = False,
        use_llm: bool = False,
        max_steps: int = DEFAULT_MAX_STEPS,
        profile: str | None = None,
        mode: str | None = None,
        **config: Any,
    ) -> "AgentSession":
        """`profile` names a balance profile (default: $CHAOS_PROFILE or "default");
        `mode` a game mode (e.g. "j54"; it sets chaos itself); `config` overrides
        any RunConfig field (start_money, target_money, ...)."""
        if seed is None:
            seed = random.randrange(2**31)
        cfg = RunConfig.from_balance(load_balance(profile), enable_chaos=chaos, seed=seed, use_llm=use_llm, **config)
        if mode:
            from chaos_blackjack.modes import get_mode

            cfg = get_mode(mode).apply(cfg)
        try:
            ctrl = GameController(cfg, save_fn=lambda d, n: n)
        except ValueError as exc:
            if use_llm and "GPTSAPI_API_KEY" in str(exc):
                raise LlmUnavailable(str(exc)) from exc
            raise
        ctrl.drain_notices()
        return cls(ctrl, seed=seed, use_llm=use_llm, max_steps=max_steps)

    # ------------------------------------------------------------ execute

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        cmd = str(command.get("cmd", "")).strip().lower()
        if cmd in ("observe", "obs", "state"):
            return self._reply()
        if cmd == "help":
            return self._reply(extra={"commands": COMMANDS})
        if cmd not in ("bet", "buy", "reroll", "act"):
            return self._error("unknown_command", f"Unknown cmd {cmd!r}. Use one of: {', '.join(COMMANDS)}")
        if self.controller.phase == TablePhase.RUN_OVER:
            return self._error("run_over", "The run is over. Start a new one.")
        if self.steps >= self.max_steps:
            return self._error("step_limit", f"Step limit {self.max_steps} reached.")

        try:
            if cmd == "bet":
                self._bet(command)
            elif cmd == "buy":
                self._buy(command)
            elif cmd == "reroll":
                self.controller.reroll_shop()
            else:
                self._act(command)
        except ActionError as e:
            return self._error("illegal_action", str(e))
        except (TypeError, ValueError) as e:
            return self._error("invalid_argument", str(e))
        self.steps += 1
        self._auto_advance()
        return self._reply()

    def _bet(self, command: dict[str, Any]) -> None:
        if "amount" not in command:
            raise ValueError("bet needs an integer 'amount'")
        amount = command["amount"]
        if isinstance(amount, bool) or not isinstance(amount, (int, str)):
            raise ValueError("amount must be an integer")
        self.last_round = None
        self.controller.place_bet(int(amount))

    def _buy(self, command: dict[str, Any]) -> None:
        item = str(command.get("item", "")).strip()
        if not item:
            raise ValueError("buy needs an 'item' id")
        self.controller.buy(item)

    def _act(self, command: dict[str, Any]) -> None:
        action = str(command.get("action", "")).strip().lower()
        if action == Action.USE_ITEM:
            item = str(command.get("item", "")).strip()
            if not item:
                raise ValueError("use_item needs an 'item' id")
            result = self.controller.use_item(item)
            if not result.ok:
                raise ActionError(result.message or f"Item {item!r} could not be used")
            return
        method = _ACT_METHODS.get(action)
        if method is None:
            raise ValueError(f"Unknown action {action!r}; expected one of {sorted([*_ACT_METHODS, Action.USE_ITEM])}")
        getattr(self.controller, method)()

    def _auto_advance(self) -> None:
        c = self.controller
        for _ in range(_MAX_AUTO_STEPS):
            if c.phase == TablePhase.CHAOS:
                c.resolve_chaos()
            elif c.phase == TablePhase.DEALER_TURN:
                c.dealer_step()
            elif c.phase == TablePhase.ROUND_OVER:
                self._record_last_round()
                c.next_round()
            else:
                break
        if c.phase == TablePhase.RUN_OVER:
            self._record_last_round()

    def _record_last_round(self) -> None:
        """Keep the settled round (with both final hands) for the next observation."""
        c = self.controller
        if c.last_result is None or c.state is None:
            return
        v = c.view()
        self.last_round = {
            **round_result_dict(c.last_result),
            "your_cards": [card_str(x) for x in v.player_cards],
            "dealer_cards": [card_str(x) for x in v.dealer_cards],
        }

    # ------------------------------------------------------------- output

    def observe(self) -> dict[str, Any]:
        return build_observation(self.controller.view(), last_round=self.last_round)

    def _reply(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": True, "events": event_texts(self.controller.drain_notices())}
        out["obs"] = self.observe()
        if extra:
            out.update(extra)
        return out

    def _error(self, code: str, message: str) -> dict[str, Any]:
        out = self._reply()
        out["ok"] = False
        out["error"] = {"code": code, "message": message, "legal_actions": out["obs"]["legal_actions"]}
        return out

    # -------------------------------------------------------- persistence

    def to_state(self) -> dict[str, Any]:
        c = self.controller
        save = build_save_data(
            run=c.run,
            state=c.state if c.phase == TablePhase.PLAYER_TURN else None,
            loop=c.loop,
            enable_chaos=c.config.enable_chaos,
            shop=c.shop,
            shop_seed=c.shop_seed,
            hole_revealed=c.hole_revealed,
            chaos_memory=c.chaos_memory.export(),
            config=c.config.to_dict(),
            table=c.table.to_dict() if c.table is not None else None,
        )
        hidden = {
            "save": save.to_dict(),
            "rng": _rng_to_json(c.rng.getstate()),
            "config": c.config.to_dict(),
        }
        return {
            "version": STATE_VERSION,
            "seed": self.seed,
            "chaos": c.config.enable_chaos,
            "use_llm": self.use_llm,
            "steps": self.steps,
            "max_steps": self.max_steps,
            "last_round": self.last_round,
            "run_end": {"kind": c.run_end.kind, "message": c.run_end.message} if c.run_end else None,
            # Deck order lives here; packed so it is not read by accident.
            "packed": base64.b64encode(zlib.compress(json.dumps(hidden).encode("utf-8"))).decode("ascii"),
        }

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> "AgentSession":
        if int(data.get("version", 0)) != STATE_VERSION:
            raise ValueError(f"Unsupported state version {data.get('version')!r}")
        hidden = json.loads(zlib.decompress(base64.b64decode(data["packed"])).decode("utf-8"))
        cfg = RunConfig.from_dict(
            hidden.get("config", {}),
            enable_chaos=bool(data.get("chaos")),
            seed=data.get("seed"), use_llm=bool(data.get("use_llm")),
        )
        use_llm = bool(data.get("use_llm"))
        ctrl = GameController.from_save(
            RunSaveData.from_dict(hidden["save"]), cfg,
            save_fn=lambda d, n: n,
        )
        ctrl.rng.setstate(_rng_from_json(hidden["rng"]))
        if data.get("run_end"):
            ctrl.run_end = RunEndResult(**data["run_end"])
            ctrl.phase = TablePhase.RUN_OVER
        ctrl.drain_notices()
        return cls(
            ctrl,
            seed=data.get("seed"),
            use_llm=use_llm,
            max_steps=int(data.get("max_steps", DEFAULT_MAX_STEPS)),
            steps=int(data.get("steps", 0)),
            last_round=data.get("last_round"),
        )


def _rng_to_json(state: tuple) -> list:
    version, internal, gauss = state
    return [version, list(internal), gauss]


def _rng_from_json(data: list) -> tuple:
    version, internal, gauss = data
    return (version, tuple(internal), gauss)
