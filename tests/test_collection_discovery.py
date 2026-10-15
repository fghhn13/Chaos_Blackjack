"""The Collection's discovery and the Shop's dealer looks (docs/design/CODEX.md "Discovery", TUTORIAL.md)."""

from __future__ import annotations

import pytest

from chaos_blackjack import meta
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.codex.discovery import Discovery
from chaos_blackjack.codex.models import CodexEntry
from chaos_blackjack.meta import onboarding
from chaos_blackjack.meta.fake import install_fake


def entry(kind, entry_id):
    return CodexEntry(kind, entry_id, entry_id.title(), "peek", "", lambda cfg: "", None)


@pytest.fixture
def guided(monkeypatch):
    monkeypatch.setenv("CHAOS_TUTORIAL", "1")
    svc = install_fake(demo=False)
    yield svc
    meta.use_service(None)


@pytest.fixture
def unguided():
    svc = install_fake(demo=False)
    yield svc
    meta.use_service(None)


def test_seen_rows_discover_entries_of_their_kind():
    d = Discovery(frozenset({("offer", "ph_margin"), ("item", "peek"), ("environment", "bust"), ("rule", "j54_burn")}))
    assert d.known(entry("build", "ph_margin")) and d.known(entry("item", "peek"))
    assert d.known(entry("environment", "bust")) and d.known(entry("rule", "j54_burn"))
    assert not d.known(entry("build", "ph_court")) and not d.known(entry("environment", "tie"))
    assert d.known(entry("mode", "chaos"))   # tables follow their tab
    assert d.count([entry("build", "ph_margin"), entry("build", "ph_court")]) == (1, 2)


def test_a_player_from_before_onboarding_sees_everything(unguided):
    p = meta.create_player(1, "Old")
    d = meta.discovery(p.id)
    assert d.all_known and d.series_state("j54") == "open"


def test_a_new_player_sees_a_silhouette_tab_and_nothing_discovered(guided):
    p = meta.create_player(1, "New")
    d = meta.discovery(p.id)
    assert d.series_state("core") == "open"
    assert d.series_state("poker_head") == "silhouette" and "top stake" in d.teasers["poker_head"]
    assert d.series_state("j54") == "hidden"
    assert not d.known(entry("item", "peek"))


def test_a_run_discovers_what_was_on_the_shelf_and_the_core_offer(guided):
    p = meta.create_player(1, "New")
    for m in (onboarding.TUTORIAL, onboarding.CLASSIC_MAX_WIN):
        meta.reach(p.id, m)
    started = meta.start_run(p.id, "chaos", stake=400)
    c = started.controller
    cores = [o.id for o in c.choice.options]
    shelf = []
    c.choose(cores[0])
    shelf = [o.item for o in c.shop.offers]
    c.run.money = 0
    c.check_terminal()
    if c.run_end is None:
        pytest.skip("this table keeps a broke run going")
    meta.finish_run(started.run_id, c)
    d = meta.discovery(p.id)
    assert d.series_state("poker_head") == "open"
    for item in [*cores[:2], *shelf]:
        if item != "cash":
            assert d.known(entry("build", item)), item


def test_dealer_looks_are_sold_after_beating_the_dealer_and_j54_looks_not_yet(guided):
    p = meta.create_player(1, "New")
    offers = {o.cosmetic.id: o for o in meta.wardrobe(p.id)}
    assert "table_j54" not in offers                      # J-54 is not even a silhouette yet
    assert offers["table_midnight"].can_buy and offers["table_midnight"].price == 600
    for m in (onboarding.CLASSIC_MAX_WIN, onboarding.POKER_HEAD_WIN):
        meta.reach(p.id, m)
    offers = {o.cosmetic.id: o for o in meta.wardrobe(p.id)}
    assert not offers["table_j54"].can_buy and offers["table_j54"].reason == "Not sold yet"
    with pytest.raises(meta.MetaError, match="Not sold yet"):
        meta.buy_cosmetic(p.id, "avatar_j54")


def test_a_player_from_before_onboarding_can_still_buy_j54_looks(unguided):
    p = meta.create_player(1, "Old")
    with meta.service()._db() as db, db:
        db.execute("UPDATE player SET tokens = 2000 WHERE id = ?", (p.id,))
    offer = {o.cosmetic.id: o for o in meta.wardrobe(p.id)}["avatar_j54"]
    assert offer.can_buy and offer.price == 1500
    meta.buy_cosmetic(p.id, "avatar_j54")


def test_poker_head_looks_wait_for_a_win(guided, monkeypatch):
    monkeypatch.setitem(onboarding.SALE_LOCKS, "core", (onboarding.POKER_HEAD_WIN, "Beat Poker Head's Table to buy this"))
    p = meta.create_player(1, "New")
    offer = {o.cosmetic.id: o for o in meta.wardrobe(p.id)}["table_midnight"]
    assert not offer.can_buy and offer.reason.startswith("Beat Poker Head")
    meta.reach(p.id, onboarding.CLASSIC_MAX_WIN)
    meta.reach(p.id, onboarding.POKER_HEAD_WIN)
    assert {o.cosmetic.id: o for o in meta.wardrobe(p.id)}["table_midnight"].can_buy
