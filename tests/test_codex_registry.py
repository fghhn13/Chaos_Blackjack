"""Reference coverage, extension points and live profile presentation."""

import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex import CodexEntry, codex_entries, codex_kinds, register_codex_provider
from chaos_blackjack.codex import registry as codex_registry
from chaos_blackjack.registry import get_registry


def test_builtins_and_tab_order():
    assert [k.id for k in codex_kinds()] == ["rule", "mode", "item", "ai", "build", "environment"]
    assert [e.id for e in codex_entries("environment")] == [
        "fixed", "shift", "bust", "tie", "bust_outcome", "profit_cap", "item_ban", "markup", "hidden"]
    assert len(codex_entries("build")) == 41
    assert len(codex_entries("rule")) == 13  # Poker Head's 7 and J-54's 6
    assert len(codex_entries("item")) == 6
    assert [e.id for e in codex_entries("mode")] == ["normal", "chaos", "j54"]
    assert [e.id for e in codex_entries("ai")] == ["default"]
    assert codex_entries("missing") == []
    for entry in codex_entries():
        assert entry.name and entry.icon and entry.summary and entry.detail(RunConfig())
        assert (entry.demo is not None) == (entry.kind in {"rule", "item"})


def test_rule_details_use_fixed_params_over_stub_proposals():
    cfg = RunConfig(chaos_rule_params={
        "modify_card_value": {"delta": 4}, "great_crash": {"ten_value": 6},
        "odd_even_chaos": {"even_delta": 5, "odd_delta": -3},
        "suit_power": {"red_delta": 3, "black_delta": -4},
        "fragile_bust": {"bust_limit": 16}, "tiebreaker_shift": {"ties_to": "player"},
    }, disabled_rules=("great_crash",))
    entries = {e.id: e for e in codex_entries("rule", cfg)}
    assert "+4 per card" in entries["modify_card_value"].detail(cfg)
    assert "value 6" in entries["great_crash"].detail(cfg)
    assert "Disabled for AI selection" in entries["great_crash"].detail(cfg)
    assert "2/4/6/8 +5, 3/5/7/9 -3" in entries["odd_even_chaos"].detail(cfg)
    assert "red suits +3, black suits -4" in entries["suit_power"].detail(cfg)
    assert "reduced to 16" in entries["fragile_bust"].detail(cfg)
    assert "ties go to Player" in entries["tiebreaker_shift"].detail(cfg)
    assert "-1 per card" in entries["modify_card_value"].detail(RunConfig())
    assert "ties go to Dealer" in entries["tiebreaker_shift"].detail(RunConfig())  # the offline AI's proposal
    dealer_ties = RunConfig(chaos_rule_params={"tiebreaker_shift": {"ties_to": "dealer"}})
    assert "ties go to Dealer" in entries["tiebreaker_shift"].detail(dealer_ties)


def test_item_details_are_live_even_on_an_existing_entry():
    oracle = next(e for e in codex_entries("item") if e.id == "fate_oracle")
    cfg = replace(RunConfig(), shop_prices={"fate_oracle": 47}, shop_bankroll_pct=(), shop_slots=4,
                  shop_refresh_rounds=5, item_params={"fate_oracle": {"cards": 6}})
    detail = oracle.detail(cfg)
    assert "next 6 cards" in detail and "47 chips" in detail
    assert "4 different items" in detail and "every 5 rounds" in detail
    assert "Not offered" in oracle.detail(replace(cfg, shop_prices={}))


def test_modes_describe_the_supplied_config():
    cfg = RunConfig(start_money=230, target_money=920, min_bet=7, max_bet_fraction=.25,
                    dealer_stand_on=19, blackjack_pays=(7, 4), allow_double=False,
                    allow_surrender=False)
    for entry in codex_entries("mode", cfg):
        detail = entry.detail(cfg)
        if entry.id == "chaos":
            assert "500 net assets" in detail
        elif entry.id == "j54":  # J-54's goal is a protocol, not a chip target
            assert "random protocol" in detail
        else:
            assert "230 chips" in detail and "into 920" in detail
        assert "Bet 7 up to 25%" in detail and "stands on 19" in detail
        assert "7:4" in detail and "No double down or surrender" in detail


def test_modes_registry_replaces_fallback_at_query_time(monkeypatch):
    module = ModuleType("chaos_blackjack.modes")
    live = [SimpleNamespace(id="custom", name="Custom table", icon="custom_icon",
                           description="A plugin mode.", overrides={"start_money": 310}, unlocked_by=None)]
    module.modes = lambda: list(live)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    entries = codex_entries("mode")
    assert [e.id for e in entries] == ["custom"]
    assert entries[0].icon == "custom_icon"
    assert "310 chips" in entries[0].detail(RunConfig())
    live.append(SimpleNamespace(id="later", name="Later", icon="later",
                               description="Added after import.", overrides={}, unlocked_by="unlock_later"))
    assert [e.id for e in codex_entries("mode")] == ["custom", "later"]


def test_new_rule_and_item_plugins_appear_without_codex_changes(monkeypatch):
    from chaos_blackjack.rules.plugins.modify_card_value import ModifyCardValueModifier

    registry = get_registry()
    monkeypatch.setitem(registry._chaos_rules, "test_rule", lambda p: ModifyCardValueModifier("test_rule", p.get("delta", 0)))
    class CustomItem:
        codex_name = "Plugin item"
        codex_icon = "plugin_icon"
        codex_summary = "A content pack item."
        codex_detail = staticmethod(lambda cfg: f"Custom price {cfg.shop_prices.get('test_item')}")
    monkeypatch.setitem(registry._items, "test_item", CustomItem)
    assert "test_rule" in {e.id for e in codex_entries("rule")}
    item = next(e for e in codex_entries("item") if e.id == "test_item")
    assert (item.name, item.icon, item.demo) == ("Plugin item", "plugin_icon", None)
    assert item.detail(RunConfig(shop_prices={"test_item": 81})) == "Custom price 81"


def test_provider_plugins_override_metadata_and_add_ai_entries(monkeypatch):
    monkeypatch.setattr(codex_registry, "_PROVIDERS", {k: list(v) for k, v in codex_registry._PROVIDERS.items()})
    extra = CodexEntry("ai", "custom_ai", "Custom AI", "custom_ai", "Plugin opponent.", lambda cfg: "Details", None)
    provider = lambda cfg: [extra]
    register_codex_provider("ai", provider)
    register_codex_provider("ai", provider)
    assert [e.id for e in codex_entries("ai")].count("custom_ai") == 1
    replacement = replace(codex_entries("rule")[0], name="Replacement", order=-1)
    register_codex_provider("rule", lambda cfg: [replacement])
    assert codex_entries("rule")[0] == replacement
    assert len(codex_entries("rule")) == 13


def test_provider_receives_config_and_rejects_wrong_kind(monkeypatch):
    monkeypatch.setattr(codex_registry, "_PROVIDERS", {k: list(v) for k, v in codex_registry._PROVIDERS.items()})
    cfg = RunConfig(start_money=211)
    seen = []
    register_codex_provider("ai", lambda supplied: seen.append(supplied) or [])
    codex_entries("ai", cfg)
    assert seen == [cfg]
    register_codex_provider("ai", lambda supplied: [codex_entries("item", supplied)[0]])
    with pytest.raises(ValueError, match="returned kind"):
        codex_entries("ai", cfg)


def test_ai_details_use_run_tuning():
    cfg = RunConfig(chaos_guidance_probability=.75, chaos_memory_enabled=True, chaos_memory_limit=12,
                    chaos_stub=(("great_crash", {}, 9.0),), disabled_rules=("fragile_bust",))
    detail = codex_entries("ai")[0].detail(cfg)
    assert "75%" in detail and "limit of 12 events" in detail
    assert "Great Crash (weight 9)" in detail and "Fragile Bust" not in detail


def test_fractional_probabilities_and_bet_limits_are_not_rounded():
    cfg = RunConfig(chaos_guidance_probability=.875, max_bet_fraction=.333)
    assert "87.5%" in codex_entries("ai")[0].detail(cfg)
    assert "33.3%" in codex_entries("mode")[0].detail(cfg)


def test_build_references_use_live_effects_prices_and_slot_limit():
    original = {e.id: e for e in codex_entries("build")}
    cfg = replace(RunConfig(), mode_settings={**RunConfig().mode_settings,
        "chaos.build_slots": 2, "chaos.margin_bonus": 3, "chaos.surrender_pct": 15,
        "chaos.approx_values": "19,22", "chaos.extra_shop_slots": 2},
        item_params={"ph_court": {"value": 4}, "ph_stock": {"payout": 120, "probability": .6},
                     "ph_loan": {"advance": 60, "repay": 80}},
        shop_prices={"ph_court": 77, "ph_stock": 45, "ph_loan": 0})
    entries = {e.id: e for e in codex_entries("build", cfg)}
    assert "by 3" in original["ph_margin"].detail(cfg)
    assert "15%" in entries["ph_retreat"].summary
    assert "19 and 22" in entries["ph_approx"].summary
    assert "2 shop" in entries["ph_account"].summary
    assert "as 4 each" in entries["ph_court"].summary
    assert "2 permanent slots" in original["ph_court"].detail(cfg)
    assert entries["ph_court"].price == "77 chips"
    assert entries["ph_stock"].price == "Invest 45 chips"
    assert "60% chance of 120" in entries["ph_stock"].summary
    assert entries["ph_loan"].price == "Borrow 60 / Repay 80"
    assert "Tuning:" not in entries["ph_court"].detail(cfg)
    assert entries["ph_oracle"].timing == "Before betting"
    assert entries["ph_buffer"].timing == "Before bet / Your turn"
    assert "Creates no Recovery Receipt" in entries["ph_waiver"].detail(cfg)
    for entry in entries.values():
        assert entry.category and entry.style and entry.timing and entry.price
        assert all(target in entries for target in entry.related)
