"""The chip vault: stakes, settling, debt, relief and lifetime spend (docs/design/META_PROGRESSION.md "Chip vault")."""

import sqlite3

import pytest

from chaos_blackjack import meta
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.data.db import migrate
from chaos_blackjack.logic.run_end_policy import RunEndResult
from chaos_blackjack.meta.fake import install_fake
from chaos_blackjack.meta.models import MetaError


@pytest.fixture()
def svc():
    s = install_fake(demo=False)
    yield s
    meta.use_service(None)


def _cards(*ranks):
    return tuple(Card(Rank(r), "♠") for r in ranks)


def _set_vault(svc, player_id, chips):
    return svc.grant_tokens(player_id, chips - meta.get_player(player_id).tokens)


def _lose(run):
    c = run.controller
    c.run.money = 0
    c.run_end = RunEndResult("defeat", "Broke")
    c.phase = TablePhase.RUN_OVER
    return meta.finish_run(run.run_id, c)


def test_a_new_player_has_a_full_vault_and_tables_name_their_stakes(svc):
    p = meta.create_player(1, "New")
    assert p.tokens == p.chips == 1000 and p.relief_streak == 0 and p.lifetime_spend == 0
    assert meta.stake_range("normal") == (40, 100) and meta.stake_range("chaos") == (400, 1000)
    assert meta.stake_range("j54") is None   # J-54's demo is a free table


def test_the_stake_leaves_the_vault_and_sets_the_run(svc):
    p = meta.create_player(1, "S")
    run = meta.start_run(p.id, "chaos", seed=4, stake=600)
    assert meta.get_player(p.id).tokens == 400
    assert run.controller.run.money == 600 and run.controller.run.target_money == 3600   # 6 x the stake
    assert run.controller.config.exit_money == 2400


@pytest.mark.parametrize("stake", [39, 101])
def test_stakes_outside_the_table_s_range_are_refused(svc, stake):
    p = meta.create_player(1, "R")
    with pytest.raises(MetaError, match="Bring 40 to 100"):
        meta.start_run(p.id, "normal", stake=stake)
    assert meta.get_player(p.id).tokens == 1000


def test_a_stake_cannot_exceed_the_vault(svc):
    p = meta.create_player(1, "V")
    _set_vault(svc, p.id, 450)
    with pytest.raises(MetaError, match="Bring 400 to 450"):
        meta.start_run(p.id, "chaos", stake=500)
    _set_vault(svc, p.id, 300)
    with pytest.raises(MetaError, match="needs at least 400"):
        meta.start_run(p.id, "chaos")


def test_a_win_brings_the_cash_home(svc):
    p = meta.create_player(1, "W")
    run = meta.start_run(p.id, "normal", seed=1, stake=100)
    c = run.controller
    c.run.money = 300
    c.place_bet(150)
    c.state = GameState(_cards("K", "Q"), _cards("10", "8"), _cards("2"), GamePhase.PLAYER_TURN)
    c.stand()
    c.finish_dealer()
    reward = meta.finish_run(run.run_id, c)
    assert reward.breakdown[0] == ("Brought home", 400)
    rec = meta.history(p.id)[0]
    assert rec.tokens_earned == 400


def test_a_defeat_loses_the_stake_and_pays_what_it_owes(svc):
    p = meta.create_player(1, "D")
    run = meta.start_run(p.id, "chaos", seed=2, stake=400)
    run.controller.table.ledger.shortfall = 150           # a fourfold loss beyond the cash
    reward = _lose(run)
    assert ("Debt paid", -150) in reward.breakdown
    assert meta.get_player(p.id).tokens == 1000 - 400 - 150


def test_debt_never_takes_the_vault_below_zero_and_relief_follows(svc):
    p = meta.create_player(1, "Z")
    run = meta.start_run(p.id, "chaos", seed=2, stake=400)
    _set_vault(svc, p.id, 30)
    run.controller.table.ledger.shortfall = 500
    reward = _lose(run)
    assert ("Debt paid", -30) in reward.breakdown and ("Relief from Poker Head", 40) in reward.breakdown
    assert meta.get_player(p.id).tokens == 40


def test_relief_grows_with_each_bankruptcy_up_to_the_cap_and_a_win_resets_it(svc):
    p = meta.create_player(1, "Broke")
    paid = []
    for _ in range(8):
        _set_vault(svc, p.id, 0)
        paid.append(meta.claim_relief(p.id))
    assert paid == [40, 50, 60, 70, 80, 90, 100, 100]
    assert meta.claim_relief(p.id) == 0                     # 100 covers Classic's minimum: nothing more
    _set_vault(svc, p.id, 100)
    run = meta.start_run(p.id, "normal", seed=1, stake=100)
    c = run.controller
    c.run_end = RunEndResult("victory", "Won")
    c.phase = TablePhase.RUN_OVER
    meta.finish_run(run.run_id, c)
    assert meta.get_player(p.id).relief_streak == 0
    _set_vault(svc, p.id, 0)
    assert meta.claim_relief(p.id) == 40


def test_relief_tops_up_to_classic_s_minimum(svc):
    p = meta.create_player(1, "Short")
    _set_vault(svc, p.id, 35)
    assert meta.claim_relief(p.id) == 40 and meta.get_player(p.id).tokens == 75
    _set_vault(svc, p.id, 39)
    assert meta.claim_relief(p.id) == 50                    # the second relief, at least 1 to reach 40


def test_abandoning_loses_the_stake(svc):
    p = meta.create_player(1, "Quit")
    run = meta.start_run(p.id, "chaos", seed=3, stake=1000)
    meta.abandon_run(run.run_id)
    assert meta.get_player(p.id).tokens == 40               # nothing left, so Poker Head's relief
    assert meta.history(p.id)[0].result == "abandoned"


def test_lifetime_spend_counts_the_run_shop_and_looks(svc):
    p = meta.create_player(1, "Spender")
    run = meta.start_run(p.id, "chaos", seed=5, stake=400)
    c = run.controller
    c.choose(c.choice.options[0].id)
    before = c.run.money                                     # after the core's own chips
    offer = next(o for o in c.view().shop_offers if o.affordable and o.kind != "finance")
    c.buy(offer.item)
    if c.choice is not None:                                 # a full build would ask; it never is here
        c.cancel_choice()
    paid = before - c.run.money
    _lose(run)
    meta.buy_cosmetic(p.id, "card_back_crimson")
    assert meta.get_player(p.id).lifetime_spend == paid + 40


def test_a_free_table_takes_no_stake(svc):
    p = meta.create_player(1, "Demo")
    run = meta.start_run(p.id, "j54", seed=1)
    assert meta.get_player(p.id).tokens == 1000
    assert run.controller.run.money == run.config.start_money


def test_the_migration_gives_every_player_1000_chips_and_keeps_worn_looks(tmp_path):
    from chaos_blackjack.data import db as dbmod

    conn = sqlite3.connect(tmp_path / "old.db")
    conn.row_factory = sqlite3.Row
    dbmod.schema_version(conn)                               # creates the version table
    for name, sql in dbmod._package_files("migrations"):  # noqa: SLF001 - a database from before 0008
        version = int(name.split("_", 1)[0])
        if version >= 8:
            break
        for statement in dbmod._statements(sql):  # noqa: SLF001
            conn.execute(statement)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.execute("INSERT INTO player (id, slot, name, tokens) VALUES (1, 1, 'Old', 60)")
    conn.execute("INSERT INTO player_loadout (player_id, slot, cosmetic_id) VALUES (1, 'table', 'table_midnight')")
    conn.commit()
    migrate(conn)
    row = conn.execute("SELECT tokens, relief_streak, lifetime_spend FROM player WHERE id = 1").fetchone()
    assert tuple(row) == (1000, 0, 0)
    assert conn.execute("SELECT cosmetic_id FROM player_cosmetic WHERE player_id = 1").fetchone()[0] == "table_midnight"


# --- early-bust insurance ---------------------------------------------------------------------------


def test_insurance_costs_6_percent_and_refunds_half_on_an_early_defeat(svc):
    p = meta.create_player(1, "Ins")
    assert meta.insurance_terms(svc._balance(svc._conn, None), 650) == (39, 325)  # noqa: SLF001
    run = meta.start_run(p.id, "chaos", seed=6, stake=400, insure=True)
    assert meta.get_player(p.id).tokens == 1000 - 400 - 24 and meta.get_player(p.id).lifetime_spend == 24
    run.controller.run.round = 2
    reward = _lose(run)
    assert ("Insurance payout", 200) in reward.breakdown and meta.get_player(p.id).tokens == 576 + 200


def test_insurance_pays_nothing_after_the_early_rounds_or_on_a_win(svc):
    p = meta.create_player(1, "Late")
    run = meta.start_run(p.id, "chaos", seed=6, stake=400, insure=True)
    run.controller.last_result = None
    run.controller.run.round = 9                             # eight rounds played
    reward = _lose(run)
    assert not any(label == "Insurance payout" for label, _ in reward.breakdown)


def test_insurance_needs_chips_beyond_the_stake_and_quitting_does_not_pay(svc):
    p = meta.create_player(1, "Thin")
    _set_vault(svc, p.id, 400)
    with pytest.raises(MetaError, match="Insurance costs 24"):
        meta.start_run(p.id, "chaos", stake=400, insure=True)
    _set_vault(svc, p.id, 1000)
    run = meta.start_run(p.id, "chaos", seed=6, stake=400, insure=True)
    meta.abandon_run(run.run_id)
    assert meta.get_player(p.id).tokens == 576


# --- membership ------------------------------------------------------------------------------------


def _spend(svc, player_id, chips):
    with svc._db() as db, db:  # noqa: SLF001
        db.execute("UPDATE player SET lifetime_spend = ? WHERE id = ?", (chips, player_id))


def test_membership_levels_follow_lifetime_spend(svc):
    p = meta.create_player(1, "M")
    for spend, level, name in ((0, 1, "Newcomer"), (999, 1, "Newcomer"), (1000, 2, "Regular"), (3000, 3, "Patron"),
                               (8000, 4, "High Roller"), (20000, 5, "Guest of Honor")):
        _spend(svc, p.id, spend)
        m = meta.membership(p.id)
        assert (m.level, m.name, m.badge) == (level, name, f"member_{level}")
    assert m.next_at is None and m.progress == 1.0
    _spend(svc, p.id, 2000)
    assert meta.membership(p.id).progress == 0.5 and meta.membership(p.id).next_at == 3000


def test_level_3_raises_the_relief_cap_and_level_4_discounts_the_shop(svc):
    p = meta.create_player(1, "Perks")
    _spend(svc, p.id, 3000)
    paid = []
    for _ in range(10):
        _set_vault(svc, p.id, 0)
        paid.append(meta.claim_relief(p.id))
    assert max(paid) == 120
    offer = {o.cosmetic.id: o for o in meta.wardrobe(p.id, "deck")}["card_back_crimson"]
    assert offer.price == 40
    _spend(svc, p.id, 8000)
    _set_vault(svc, p.id, 1000)
    offer = {o.cosmetic.id: o for o in meta.wardrobe(p.id, "deck")}["card_back_crimson"]
    assert offer.price == 38 and offer.unlock_hint.startswith("38 chips")
    meta.buy_cosmetic(p.id, "card_back_crimson")
    assert meta.get_player(p.id).tokens == 962 and meta.get_player(p.id).lifetime_spend == 8038
