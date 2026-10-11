"""An AI's prompt, permissions and fresh offline backend factory, plus an
optional table persona (name, portraits and lines) for front-ends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from chaos_blackjack.ai.chaos_policy import ChaosPolicy
from chaos_blackjack.ai.chaos_scheduler import ChaosScheduler
from chaos_blackjack.ai.pipeline import ChaosPipeline
from chaos_blackjack.contracts.llm import LLMBackend
from chaos_blackjack.registry.registry import Registry


# Portrait files contributed by personas: asset id -> image file. Front-ends
# look here after their own asset folders (see gui/assets/manager.py).
_PERSONA_IMAGES: dict[str, Path] = {}

# Table events a persona can react to (mood) and speak about (lines).
PERSONA_EVENTS = (
    "idle", "off", "round_started", "rule_applied", "narration", "poke", "item_used",
    "player_bust", "player_blackjack", "dealer_blackjack", "dealer_busts",
    "outcome_dealer", "outcome_player", "outcome_blackjack", "outcome_push", "outcome_surrender",
)


def persona_image(asset_id: str) -> Path | None:
    return _PERSONA_IMAGES.get(asset_id)


@dataclass(frozen=True)
class Persona:
    """How an AI looks and talks at the table. Presentation only: it never
    changes what the AI may do (that is `AIProfile.permissions`).

    `portraits` maps an expression name to an image file; `moods` maps a table
    event (PERSONA_EVENTS) to an expression; `lines` maps an event to lines the
    front-end rotates through (`rule_applied` may use `{rule}`). Events without
    a mood keep the current expression; events without lines keep the speech.
    """

    id: str
    name: str
    portraits: dict[str, Path]
    moods: dict[str, str] = field(default_factory=dict)
    lines: dict[str, tuple[str, ...]] = field(default_factory=dict)
    default: str = "neutral"

    def __post_init__(self) -> None:
        if self.default not in self.portraits:
            raise ValueError(f"Persona {self.id}: no portrait for the default expression {self.default!r}")
        unknown = (set(self.moods) | set(self.lines)) - set(PERSONA_EVENTS)
        if unknown:
            raise ValueError(f"Persona {self.id}: unknown events {sorted(unknown)}")
        missing = set(self.moods.values()) - set(self.portraits)
        if missing:
            raise ValueError(f"Persona {self.id}: moods use expressions without portraits {sorted(missing)}")
        for expression, path in self.portraits.items():
            _PERSONA_IMAGES[self.asset_id(expression)] = Path(path)

    def asset_id(self, expression: str) -> str:
        return f"{self.id}_{expression if expression in self.portraits else self.default}"

    def line(self, event: str, turn: int = 0) -> str | None:
        options = self.lines.get(event)
        return options[turn % len(options)] if options else None


@dataclass(frozen=True)
class AIProfile:
    description: str
    prompt: str
    permissions: dict[str, Any]
    offline_backend: Callable[[], LLMBackend]
    persona: Persona | None = None

    # Read by the codex (getattr with fallbacks) for pack AIs.
    @property
    def codex_name(self) -> str | None:
        return self.persona.name if self.persona else None

    @property
    def codex_icon(self) -> str:
        return self.persona.asset_id(self.persona.default) if self.persona else "chaos_calm"

    def build(self, registry: Registry, *, llm: LLMBackend | None = None) -> ChaosPipeline:
        policy = ChaosPolicy.from_profile(self.permissions)
        return ChaosPipeline(
            permission_profile=self.permissions,
            policy=policy,
            scheduler=ChaosScheduler(policy),
            prompt_name="",
            llm=llm if llm is not None else self.offline_backend(),
            registry=registry,
            system_prompt=self.prompt,
        )


def build_pipeline(ai_id: str, registry: Registry, *, use_llm: bool | None = False) -> ChaosPipeline:
    from chaos_blackjack.ai.pipeline import OfflineChaosStub

    backend = None
    if use_llm:
        from chaos_blackjack.ai.env import load_dotenv_from_project_root
        from chaos_blackjack.ai.gptsapi_llm import try_create_gptsapi_llm

        load_dotenv_from_project_root()
        backend = try_create_gptsapi_llm()
        if backend is None:
            raise ValueError("Real LLM requested but GPTSAPI_API_KEY is not configured")
    if ai_id == "default":
        if use_llm is None:
            # Preserve the original GUI/controller environment opt-in. Pack AIs
            # and AgentSession always use an explicit choice instead.
            from chaos_blackjack.core.game_loop import _default_llm

            backend = _default_llm()
        return ChaosPipeline.from_profile_name(
            "easy", "chaotic", backend if backend is not None else OfflineChaosStub(), registry,
        )
    profile = registry.resolve_ai(ai_id)
    if not isinstance(profile, AIProfile):
        raise ValueError(f"Unknown AI id: {ai_id}. Load its content pack first.")
    return profile.build(registry, llm=backend)
