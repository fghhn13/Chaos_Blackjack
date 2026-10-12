"""Cosmetics, lifetime stats and achievements (docs/design/COSMETICS_ACHIEVEMENTS.md)."""

from __future__ import annotations

import json

import pytest

from chaos_blackjack import meta
from chaos_blackjack.achievements import (
    Achievement, AchievementContext, RunFacts, achievements_catalog, get_achievement, get_stat, register_achievement,
    stats,
)
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import RoundResult
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.cosmetics import (
    COSMETIC_SLOTS, SLOT_ASSETS, Cosmetic, cosmetics, default_cosmetic, get_cosmetic, register_cosmetic,
)
from chaos_blackjack.data import clone_profile, connect, default_balance
from chaos_blackjack.data.__main__ import main as data_cli
from chaos_blackjack.data.admin import export_seed, profile_values, set_value
from chaos_blackjack.data.balance import load_balance
from chaos_blackjack.meta import MetaError, MetaService
from chaos_blackjack.meta.fake import install_fake
from chaos_blackjack.meta.tracker import RunTracker


@pytest.fixture()
def svc():
    s = install_fake(demo=False)
    yield s
    meta.use_service(None)


def _cards(*ranks: str) -> tuple[Card, ...]:
    return tuple(Card(Rank(r), "♠") for r in ranks)


def _win_run(svc: MetaService, player_id: int):
    """Start a Classic run and win it in one rigged hand."""
    run = meta.start_run(player_id, "normal", seed=1)
    c = run.controller
    c.run.money = 300
    c.place_bet(150)
    c.state = GameState(_cards("K", "Q"), _cards("10", "8"), _cards("2"), GamePhase.PLAYER_TURN)
    c.stand()
    c.finish_dealer()
    assert c.run_end is not None and c.run_end.kind == "victory"
    return run, meta.finish_run(run.run_id, c)


def _history_row(svc: MetaService, player_id: int, result: str, mode: str = "normal", **summary) -> None:
    with svc._db() as db, db:  # noqa: SLF001 - history without playing runs
        db.execute(
            "INSERT INTO run_history (player_id, ended_at, mode, result, rounds, final_money, peak_money, "
            "tokens_earned, summary) VALUES (?, datetime('now'), ?, ?, 10, 0, 150, 0, ?)",
            (player_id, mode, result, json.dumps(summary)),
        )


# ------------------------------------------------------------- catalogs (§7)


def test_every_slot_has_exactly_one_default_covering_its_assets() -> None:
    for slot in COSMETIC_SLOTS:
        defaults = [c for c in cosmetics(slot) if c.default]
        assert len(defaults) == 1, slot
        assert defaults[0].asset_map() == {a: a for a in SLOT_ASSETS[slot]}
    for c in cosmetics():
        assert set(c.asset_map()) == set(SLOT_ASSETS[c.slot])
        assert c.preview_asset in c.asset_map().values() or c.preview


def test_registries_reject_inconsistent_entries() -> None:
    with pytest.raises(ValueError, match="unknown slot"):
        register_cosmetic(Cosmetic("x", "hat", "X"))
    with pytest.raises(ValueError, match="not card_back assets"):
        register_cosmetic(Cosmetic("x", "card_back", "X", assets={"chip_1": "x_1"}))
    with pytest.raises(ValueError, match="exactly one"):
        register_achievement(Achievement("x", "X", ""))
    with pytest.raises(ValueError, match="unknown stat"):
        register_achievement(Achievement("x", "X", "", stat="nope"))
    with pytest.raises(ValueError, match="goal"):
        register_achievement(Achievement("x", "X", "", stat="runs", goal=0))
    assert get_cosmetic("x") is None and get_achievement("x") is None


def test_achievements_name_known_stats() -> None:
    for a in achievements_catalog():
        assert (a.stat is None) != (a.check is None)
        if a.stat:
            assert get_stat(a.stat) is not None
        progress, goal = a.progress(AchievementContext())
        assert progress == 0 and goal >= 1, a.id


def test_seed_rows_name_registered_entries_and_every_look_is_obtainable() -> None:
    b = default_balance()
    sold = {p.cosmetic_id for p in b.cosmetic_prices}
    rewarded = {r.cosmetic_id for r in b.achievement_rewards if r.cosmetic_id}
    assert all(get_cosmetic(c) is not None and not get_cosmetic(c).default for c in sold | rewarded)
    assert all(get_achievement(r.achievement_id) is not None for r in b.achievement_rewards)
    for c in cosmetics():
        assert c.default or c.id in sold | rewarded, f"{c.id} cannot be obtained"
    # "Most achievements pay tokens"
    assert sum(1 for r in b.achievement_rewards if r.tokens) > len(b.achievement_rewards) // 2


# ------------------------------------------------------------------ wardrobe


def test_defaults_are_owned_and_equipped(svc) -> None:
    p = meta.create_player(1, "A")
    assert meta.loadout(p.id) == {slot: default_cosmetic(slot).id for slot in COSMETIC_SLOTS}
    assert meta.asset_aliases(p.id) == {}
    assert p.avatar == "avatar"
    offers = meta.wardrobe(p.id)
    assert {o.cosmetic.id for o in offers if o.owned} == {default_cosmetic(s).id for s in COSMETIC_SLOTS}
    assert all(o.equipped == o.cosmetic.default for o in offers)
    # Hidden cosmetics stay out of the list until owned.
    assert "avatar_joker" not in {o.cosmetic.id for o in offers}
    with pytest.raises(MetaError, match="slot"):
        meta.wardrobe(p.id, "hat")


def test_buying_and_equipping(svc) -> None:
    p = meta.create_player(1, "A")
    offer = {o.cosmetic.id: o for o in meta.wardrobe(p.id, "card_back")}["card_back_crimson"]
    assert (offer.price, offer.can_buy, offer.reason, offer.unlock_hint) == (40, False, "Needs 40 tokens", "40 tokens")
    with pytest.raises(MetaError, match="Needs 40"):
        meta.buy_cosmetic(p.id, "card_back_crimson")
    with pytest.raises(MetaError, match="do not own"):
        meta.equip(p.id, "card_back_crimson")
    svc.grant_tokens(p.id, 50)
    assert meta.buy_cosmetic(p.id, "card_back_crimson").tokens == 10
    with pytest.raises(MetaError, match="already own"):
        meta.buy_cosmetic(p.id, "card_back_crimson")
    with pytest.raises(MetaError, match="not for sale"):
        meta.buy_cosmetic(p.id, "card_back_royal")
    with pytest.raises(MetaError, match="already own"):
        meta.buy_cosmetic(p.id, "card_back_standard")
    with pytest.raises(MetaError, match="Unknown cosmetic"):
        meta.buy_cosmetic(p.id, "nope")
    assert meta.equip(p.id, "card_back_crimson")["card_back"] == "card_back_crimson"
    assert meta.asset_aliases(p.id) == {"card_back": "card_back_crimson"}
    assert meta.equip(p.id, "card_back_standard")["card_back"] == "card_back_standard"
    assert meta.asset_aliases(p.id) == {}


def test_chip_sets_and_avatars_alias_every_asset(svc) -> None:
    p = meta.create_player(1, "A")
    svc.grant_cosmetic(p.id, "chips_neon")
    svc.grant_cosmetic(p.id, "avatar_spade")
    assert svc.grant_cosmetic(p.id, "avatar_spade") is False
    meta.equip(p.id, "chips_neon")
    meta.equip(p.id, "avatar_spade")
    assert meta.asset_aliases(p.id) == {
        "chip_1": "chips_neon_1", "chip_5": "chips_neon_5", "chip_10": "chips_neon_10", "chip_25": "chips_neon_25",
        "avatar": "avatar_spade"}
    assert meta.get_player(p.id).avatar == "avatar_spade"


def test_unknown_or_removed_cosmetics_fall_back_to_the_default(svc) -> None:
    p = meta.create_player(1, "A")
    with svc._db() as db, db:  # noqa: SLF001 - a cosmetic a content pack no longer registers
        db.execute("INSERT INTO player_cosmetic (player_id, cosmetic_id, source) VALUES (?, 'gone', 'shop')", (p.id,))
        db.execute("INSERT INTO player_loadout (player_id, slot, cosmetic_id) VALUES (?, 'table', 'gone')", (p.id,))
    assert meta.loadout(p.id)["table"] == "table_standard"
    assert "gone" not in {o.cosmetic.id for o in meta.wardrobe(p.id)}


def test_prices_come_from_the_balance_profile(svc, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAOS_DB", str(tmp_path / "g.db"))
    conn = connect()
    clone_profile(conn, "default", "cheap")
    set_value(conn, "cheap", "cosmetic.table_midnight.cost", "5")
    set_value(conn, "cheap", "cosmetic.chips_neon.enabled", "0")
    set_value(conn, "cheap", "reward.first_win.tokens", "99")
    with pytest.raises(Exception, match="no value"):
        set_value(conn, "cheap", "cosmetic.nope.cost", "5")
    b = load_balance("cheap", conn)
    assert {p.cosmetic_id: p.cost for p in b.cosmetic_prices}["table_midnight"] == 5
    assert "chips_neon" not in {p.cosmetic_id for p in b.cosmetic_prices}
    assert profile_values(conn, "cheap")["reward.first_win.tokens"] == "99"
    assert "INSERT INTO cosmetic_price" in export_seed(conn, "cheap")
    assert "INSERT INTO achievement_reward" in export_seed(conn, "cheap")
    s = MetaService(conn)
    p = s.create_player(1, "A")
    s.grant_tokens(p.id, 5)
    offers = {o.cosmetic.id: o for o in s.wardrobe(p.id, profile="cheap")}
    assert offers["table_midnight"].can_buy and offers["chips_neon"].price is None
    assert s.buy_cosmetic(p.id, "table_midnight", profile="cheap").tokens == 0
    conn.close()


# ------------------------------------------------------- stats and achievements


def test_victory_unlocks_once_and_pays_rewards(svc) -> None:
    p = meta.create_player(1, "W")
    run, reward = _win_run(svc, p.id)
    assert {u.achievement_id for u in reward.unlocked} == {"first_win", "bare_hands"}
    assert ("Achievement: First Win", 10) in reward.breakdown
    assert reward.tokens == sum(t for _, t in reward.breakdown) == reward.player.tokens
    # run_history keeps the run's own tokens; achievement tokens are paid on top.
    assert meta.history(p.id)[0].tokens_earned == reward.tokens - sum(u.tokens for u in reward.unlocked)
    states = {s.achievement.id: s for s in meta.achievements(p.id)}
    assert states["first_win"].unlocked and states["first_win"].progress == 1
    assert not states["regular"].unlocked and (states["regular"].progress, states["regular"].goal) == (1, 10)
    # A second win does not unlock or pay them again.
    _, again = _win_run(svc, p.id)
    assert again.unlocked == () and again.tokens == 10
    assert meta.player_stats(p.id)["victories_normal"] == 2


def test_cosmetic_rewards_are_owned_and_equippable(svc) -> None:
    p = meta.create_player(1, "C")
    _history_row(svc, p.id, "victory", mode="chaos")
    states = {s.achievement.id: s for s in meta.achievements(p.id)}
    assert states["chaos_conqueror"].unlocked and states["chaos_conqueror"].reward_cosmetic == "table_chaos"
    offer = {o.cosmetic.id: o for o in meta.wardrobe(p.id, "table")}["table_chaos"]
    assert offer.owned and not offer.can_buy and offer.unlock_hint == "Achievement: Chaos Conqueror"
    assert meta.equip(p.id, "table_chaos")["table"] == "table_chaos"


def test_run_scope_uses_the_best_run_and_total_scope_the_sum(svc) -> None:
    p = meta.create_player(1, "S")
    _history_row(svc, p.id, "defeat", blackjacks=2)
    _history_row(svc, p.id, "defeat", blackjacks=2)
    states = {s.achievement.id: s for s in meta.achievements(p.id)}
    assert states["natural_talent"].progress == 2 and not states["natural_talent"].unlocked   # best run: 2 of 3
    assert states["blackjack_collector"].progress == 4                                           # total: 4 of 50


def test_backfill_builds_stats_from_old_history_once(svc) -> None:
    p = meta.create_player(1, "Old")
    _history_row(svc, p.id, "victory", mode="chaos", items_used={"peek": 1}, surrenders=30)
    _history_row(svc, p.id, "abandoned", surrenders=50)
    states = {s.achievement.id: s for s in meta.achievements(p.id)}
    assert states["first_win"].unlocked and states["chaos_conqueror"].unlocked and states["white_flag"].unlocked
    assert not states["bare_hands"].unlocked             # an item was used
    totals = meta.player_stats(p.id)
    assert totals["runs"] == 1 and totals["surrenders"] == 30   # abandoned runs count for nothing
    player = meta.get_player(p.id)
    assert player.tokens == 10 + 10 + 5
    assert {o.cosmetic.id for o in meta.wardrobe(p.id) if o.owned} >= {"table_chaos", "avatar_joker"}
    meta.achievements(p.id)
    assert meta.get_player(p.id).tokens == player.tokens   # no second payout


def test_backfill_runs_before_the_first_settled_run(svc) -> None:
    p = meta.create_player(1, "Old")
    _history_row(svc, p.id, "victory")
    _, reward = _win_run(svc, p.id)
    assert meta.player_stats(p.id)["victories"] == 2
    assert "first_win" in {u.achievement_id for u in reward.unlocked}


def test_custom_check_achievement_reads_codex_seen(svc) -> None:
    p = meta.create_player(1, "R")
    with svc._db() as db, db:  # noqa: SLF001
        for rule in ("great_crash", "suit_power", "fragile_bust", "reverse_bust", "odd_even_chaos"):
            db.execute("INSERT INTO codex_seen (player_id, kind, entry_id) VALUES (?, 'rule', ?)", (p.id, rule))
    _, reward = _win_run(svc, p.id)
    assert "rule_scholar" in {u.achievement_id for u in reward.unlocked}


def test_tracker_counts_hands_won_five_card_hands_and_streak(svc) -> None:
    p = meta.create_player(1, "T")
    c: GameController = meta.start_run(p.id, "normal", seed=5).controller
    tracker = RunTracker(c)
    for streak, (outcome, hand) in enumerate(
            (("player", ("2", "3", "4", "5", "6")), ("blackjack", ("A", "K")), ("dealer", ("K", "Q", "5"))), 1):
        c.state = GameState(_cards(*hand), _cards("10", "7"), (), GamePhase.RESOLVED)
        c.run.win_streak = streak if outcome != "dealer" else 0
        result = RoundResult(streak, outcome, 21, 17, False, 5, 5, 100)
        c._notify(NoticeKind.ROUND_SETTLED, data={"result": result})  # noqa: SLF001
    s = tracker.summary()
    assert (s["hands_won"], s["five_card_hands"], s["win_streak"]) == (2, 1, 2)
    facts = RunFacts("normal", "defeat", summary=s)
    assert facts.count("hands_won") == 2 and facts.count("items_used") == 0
    tracker.detach()


def test_delete_player_removes_everything(svc) -> None:
    p = meta.create_player(1, "D")
    _win_run(svc, p.id)
    meta.delete_player(p.id)
    with svc._db() as db:  # noqa: SLF001
        for table in ("player_cosmetic", "player_loadout", "player_stat", "player_achievement"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_fake_demo_has_cosmetics_and_achievements() -> None:
    install_fake()
    try:
        ace = meta.list_slots()[0].player
        assert meta.loadout(ace.id)["card_back"] == "card_back_crimson"
        assert any(s.unlocked for s in meta.achievements(ace.id))
    finally:
        meta.use_service(None)


def test_every_stat_has_a_label() -> None:
    assert all(s.label for s in stats())


def test_data_cli(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CHAOS_DB", str(tmp_path / "g.db"))
    s = MetaService()
    s.create_player(1, "Cli")
    assert data_cli(["grant-cosmetic", "1", "chips_neon"]) == 0
    assert data_cli(["cosmetics", "1"]) == 0
    assert data_cli(["achievements", "1"]) == 0
    out = capsys.readouterr().out
    assert "chips_neon granted" in out and "Neon Chips" in out and "First Win" in out
