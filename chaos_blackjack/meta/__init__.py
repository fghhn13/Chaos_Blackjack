"""Meta progression: player slots, tokens, upgrades, runs and history.

Front-ends call these functions; they use one MetaService on data/game.db
(or $CHAOS_DB). `use_service(MetaService(conn))` swaps it, e.g.
`chaos_blackjack.meta.fake.install_fake()` for GUI work without a database.
Contracts: docs/design/META_PROGRESSION.md §5.1 and
docs/design/COSMETICS_ACHIEVEMENTS.md §6 (wardrobe, equip, achievements).

    slot = meta.list_slots()[0]
    player = slot.player or meta.create_player(1, "Ace")
    run = meta.start_run(player.id, "chaos", consumables=["start_peek"])
    ...play run.controller until it is over...
    reward = meta.finish_run(run.run_id, run.controller)
"""

from __future__ import annotations

from collections.abc import Iterable

from chaos_blackjack.meta.effects import Effect, effect_ids, get_effect, register_effect
from chaos_blackjack.meta.models import (
    SLOTS, AchievementState, CosmeticOffer, MetaError, PendingRun, Player, PlayerSlot, PlayerStats, RunRecord,
    RunReward, RunStart, Unlock, UpgradeOffer,
)
from chaos_blackjack.meta.service import (
    LoopFactory, MetaService, ModeOption, build_run_config, consolation_tokens, insurance_terms, reward_tokens,
)

_service: MetaService | None = None


def service() -> MetaService:
    global _service
    if _service is None:
        _service = MetaService()
    return _service


def use_service(svc: MetaService | None) -> None:
    """Install a service (None = back to data/game.db)."""
    global _service
    _service = svc


def list_slots() -> list[PlayerSlot]:
    return service().list_slots()


def create_player(slot: int, name: str) -> Player:
    return service().create_player(slot, name)


def rename_player(player_id: int, name: str) -> Player:
    return service().rename_player(player_id, name)


def delete_player(player_id: int) -> None:
    service().delete_player(player_id)


def get_player(player_id: int) -> Player:
    return service().get_player(player_id)


def meta_shop(player_id: int, profile: str | None = None) -> list[UpgradeOffer]:
    return service().meta_shop(player_id, profile)


def buy_upgrade(player_id: int, upgrade_id: str, profile: str | None = None) -> Player:
    return service().buy_upgrade(player_id, upgrade_id, profile)


def modes(player_id: int | None = None) -> list[ModeOption]:
    return service().modes(player_id)


def discovery(player_id: int | None):
    return service().discovery(player_id)


def milestones(player_id: int) -> frozenset[str]:
    return service().milestones(player_id)


def reach(player_id: int, milestone: str) -> bool:
    return service().reach(player_id, milestone)


def start_run(player_id: int, mode_id: str, *, consumables: Iterable[str] = (), profile: str | None = None,
              seed: int | None = None, loop_factory: LoopFactory | None = None, stake: int | None = None,
              insure: bool = False) -> RunStart:
    return service().start_run(player_id, mode_id, consumables=consumables, profile=profile, seed=seed,
                               loop_factory=loop_factory, stake=stake, insure=insure)


def stake_range(mode_id: str, profile: str | None = None) -> tuple[int, int] | None:
    """(min, max) chips a run of this mode brings from the vault; None = a free table."""
    return service().stake_range(mode_id, profile)


def membership(player_id: int, profile: str | None = None):
    """The player's membership level (meta/membership.py) from their lifetime spend."""
    return service().membership(player_id, profile)


def claim_relief(player_id: int, profile: str | None = None) -> int:
    """Poker Head's relief when the vault cannot cover Classic's minimum stake (0 if not needed)."""
    return service().claim_relief(player_id, profile)


def pending_run(player_id: int) -> PendingRun | None:
    return service().pending_run(player_id)


def resume_run(player_id: int, *, loop_factory: LoopFactory | None = None) -> RunStart | None:
    return service().resume_run(player_id, loop_factory=loop_factory)


def finish_run(run_id: int, controller) -> RunReward:
    return service().finish_run(run_id, controller)


def abandon_run(run_id: int) -> None:
    service().abandon_run(run_id)


def history(player_id: int, limit: int = 50) -> list[RunRecord]:
    return service().history(player_id, limit)


def codex_seen(player_id: int) -> dict[tuple[str, str], int]:
    return service().codex_seen(player_id)


def wardrobe(player_id: int, slot: str | None = None, profile: str | None = None) -> list[CosmeticOffer]:
    return service().wardrobe(player_id, slot, profile)


def loadout(player_id: int) -> dict[str, str]:
    return service().loadout(player_id)


def asset_aliases(player_id: int) -> dict[str, str]:
    return service().asset_aliases(player_id)


def equip(player_id: int, cosmetic_id: str) -> dict[str, str]:
    return service().equip(player_id, cosmetic_id)


def buy_cosmetic(player_id: int, cosmetic_id: str, profile: str | None = None) -> Player:
    return service().buy_cosmetic(player_id, cosmetic_id, profile)


def achievements(player_id: int, profile: str | None = None) -> list[AchievementState]:
    return service().achievements(player_id, profile)


def player_stats(player_id: int, *, best: bool = False) -> dict[str, int]:
    return service().player_stats(player_id, best=best)


__all__ = [
    "SLOTS", "AchievementState", "CosmeticOffer", "Effect", "MetaError", "MetaService", "ModeOption", "PendingRun",
    "Player", "PlayerSlot", "PlayerStats", "RunRecord", "RunReward", "RunStart", "Unlock", "UpgradeOffer",
    "abandon_run", "achievements", "asset_aliases", "build_run_config", "buy_cosmetic", "buy_upgrade",
    "codex_seen", "equip", "loadout", "player_stats", "reward_tokens", "wardrobe",
    "consolation_tokens", "create_player", "delete_player", "effect_ids", "finish_run", "get_effect",
    "get_player", "history", "list_slots", "meta_shop", "modes", "pending_run", "register_effect", "rename_player",
    "resume_run", "service", "start_run", "use_service", "stake_range", "claim_relief", "insurance_terms", "membership",
    "discovery", "milestones", "reach",
]
