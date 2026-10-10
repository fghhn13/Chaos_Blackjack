"""An AI's prompt, permissions and fresh offline backend factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from chaos_blackjack.ai.chaos_policy import ChaosPolicy
from chaos_blackjack.ai.chaos_scheduler import ChaosScheduler
from chaos_blackjack.ai.pipeline import ChaosPipeline
from chaos_blackjack.contracts.llm import LLMBackend
from chaos_blackjack.registry.registry import Registry


@dataclass(frozen=True)
class AIProfile:
    description: str
    prompt: str
    permissions: dict[str, Any]
    offline_backend: Callable[[], LLMBackend]

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
