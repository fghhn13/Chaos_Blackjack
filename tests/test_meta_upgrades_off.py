"""Meta upgrades are off in this version (meta.upgrades_enabled = 0): nothing is sold and owned ones do nothing.

The rest of the suite runs with CHAOS_META_UPGRADES=1 (conftest) so the dormant system keeps its tests.
"""

from types import SimpleNamespace

import pytest

from chaos_blackjack.data.balance import _load
from chaos_blackjack.data.db import MEMORY, connect
from chaos_blackjack.meta import build_run_config
from chaos_blackjack.modes import get_mode


@pytest.fixture
def shipped(monkeypatch):
    monkeypatch.delenv("CHAOS_META_UPGRADES", raising=False)
    conn = connect(MEMORY)
    try:
        yield _load(conn, "default")
    finally:
        conn.close()


def test_the_shipped_profile_sells_no_meta_upgrades(shipped):
    assert not shipped.meta_upgrades_enabled and shipped.meta_upgrades == ()


def test_owned_upgrades_and_starter_items_do_nothing(shipped):
    mode = get_mode("normal")
    plain, _ = build_run_config(shipped, mode, {})
    owned, applied = build_run_config(shipped, mode, {"start_money": 3, "bag_space": 2, "start_peek": 2})
    assert applied == {} and owned.start_money == plain.start_money and owned.bring_kinds == plain.bring_kinds


def test_the_shop_shows_only_cosmetics(shipped):
    pytest.importorskip("pygame")
    from chaos_blackjack.gui.scenes.meta_shop import MetaShopScene

    scene = MetaShopScene.__new__(MetaShopScene)
    scene.app = SimpleNamespace(balance=shipped)
    assert scene.areas == (("cosmetics", "Cosmetics"),)


def test_the_development_switch_turns_them_back_on(monkeypatch):
    monkeypatch.setenv("CHAOS_META_UPGRADES", "1")
    conn = connect(MEMORY)
    try:
        b = _load(conn, "default")
    finally:
        conn.close()
    assert b.meta_upgrades_enabled and {u.upgrade_id for u in b.meta_upgrades} >= {"start_money", "bag_space"}
