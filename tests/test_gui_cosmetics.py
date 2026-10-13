"""Cosmetic art in the GUI: manifest coverage, asset aliases and the equipped loadout."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack import meta  # noqa: E402
from chaos_blackjack.app.config import RunConfig  # noqa: E402
from chaos_blackjack.cosmetics import SLOT_ASSETS, cosmetics  # noqa: E402
from chaos_blackjack.gui.app import App  # noqa: E402
from chaos_blackjack.gui.assets import MANIFEST, AssetManager  # noqa: E402
from chaos_blackjack.gui.components.lobby import apply_loadout, choose_player, current_player  # noqa: E402
from chaos_blackjack.gui.settings import GuiSettings  # noqa: E402
from chaos_blackjack.meta.fake import install_fake  # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from chaos_blackjack.meta import MetaService

    # The shop and wardrobe flows are tested with the shipped "every look unlocked" switch off.
    monkeypatch.setattr(MetaService, "_all_looks", classmethod(lambda cls, db, profile=None: False))
    svc = install_fake()
    a = App(GuiSettings(asset_dirs=(tmp_path,)), run_config=RunConfig(use_llm=False))
    yield a
    a.audio.close()
    svc._conn.close()  # noqa: SLF001
    meta.use_service(None)
    pygame.quit()


def test_every_slot_asset_and_built_in_look_has_art_of_the_base_kind() -> None:
    for slot, bases in SLOT_ASSETS.items():
        for base in bases:
            assert base in MANIFEST, base
    for c in cosmetics():
        for base, asset in c.asset_map().items():
            assert asset in MANIFEST, f"{c.id}: {asset} has no placeholder"
            assert (MANIFEST[asset].category, MANIFEST[asset].size) == (MANIFEST[base].category, MANIFEST[base].size)


def test_aliases_redirect_images_and_fall_back_without_art(tmp_path) -> None:
    pygame.init()
    assets = AssetManager((tmp_path,))
    base = assets.image("card_back", (64, 96))
    assets.set_aliases({"card_back": "card_back_crimson", "chip_1": "no_such_art", "chip_5": "chip_5"})
    assert assets.aliases == {"card_back": "card_back_crimson", "chip_1": "no_such_art"}
    assert assets.resolve("card_back") == "card_back_crimson"
    assert assets.image("card_back", (64, 96)) is assets.image("card_back_crimson", (64, 96))
    assert assets.image("card_back", (64, 96)) is not base
    assert assets.resolve("chip_1") == "chip_1"          # missing skin art: the base look
    assert assets.source("card_back") == "placeholder"   # validation reports the base id itself
    assets.set_aliases({})
    assert assets.image("card_back", (64, 96)) is base


def test_a_skin_file_wins_over_its_placeholder(tmp_path) -> None:
    pygame.init()
    art = pygame.Surface((10, 15))
    art.fill((1, 2, 3))
    pygame.image.save(art, str(tmp_path / "card_back_neon.png"))
    assets = AssetManager((tmp_path,))
    assets.set_aliases({"card_back": "card_back_neon"})  # not in the manifest, but shipped as a file
    assert assets.image("card_back").get_size() == (10, 15)


def test_choosing_a_player_applies_their_loadout(app) -> None:
    ace = meta.list_slots()[0].player  # the fake equips Crimson Lattice and Chaos Velvet
    choose_player(app, ace.id)
    assert app.assets.aliases == {"card_back": "card_back_crimson", "table_background": "table_poker_head"}
    rookie = meta.list_slots()[1].player
    choose_player(app, rookie.id)
    assert app.assets.aliases == {}
    app.session["player_id"] = ace.id
    assert current_player(app).id == ace.id and app.assets.resolve("card_back") == "card_back_crimson"
    choose_player(app, None)
    assert app.assets.aliases == {}


def test_equipping_then_applying_changes_what_the_table_draws(app) -> None:
    rookie = meta.list_slots()[1].player
    meta.service().grant_cosmetic(rookie.id, "chips_neon")
    meta.equip(rookie.id, "chips_neon")
    apply_loadout(app, rookie.id)
    assert {app.assets.resolve(f"chip_{v}") for v in (1, 5, 10, 25)} == {
        "chips_neon_1", "chips_neon_5", "chips_neon_10", "chips_neon_25"}
    apply_loadout(app, 999_999)   # an unknown player shows the default looks
    assert app.assets.aliases == {}


def test_player_avatar_is_drawable(app) -> None:
    ace = meta.list_slots()[0].player
    meta.service().grant_cosmetic(ace.id, "avatar_spade")
    meta.equip(ace.id, "avatar_spade")
    avatar = meta.get_player(ace.id).avatar
    assert avatar == "avatar_spade" and app.assets.image(avatar, (64, 64)).get_size() == (64, 64)


# ------------------------------------------------------------------- screens


def _screen(app, name, **params):
    import chaos_blackjack.gui.scenes  # noqa: F401

    app.scenes.reset(name, **params)
    app.scenes.apply_pending()
    app._render()  # noqa: SLF001
    return app.scenes.top


def _click(app, button):
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        app.scenes.handle_event(pygame.event.Event(kind, pos=button.rect.center, button=1))
    app.scenes.apply_pending()
    app._render()  # noqa: SLF001


def test_badge_opens_profile_with_avatar_and_record(app) -> None:
    home = _screen(app, "home")
    assert home.badge.avatar == home.player.avatar
    _click(app, home.badge)
    profile = app.scenes.top
    assert type(profile).__name__ == "ProfileScene" and profile.title == home.player.name
    assert set(profile.tabs) == {"overview", "wardrobe", "achievements"}
    assert profile.all_looks >= 4 and profile.totals["runs"] == 3


def test_looks_are_bought_in_the_shop_and_switched_in_the_wardrobe(app) -> None:
    rookie = meta.list_slots()[1].player
    choose_player(app, rookie.id)
    shop = _screen(app, "meta_shop", player_id=rookie.id, area="cosmetics", series="core")
    row = shop.rows["card_back_crimson"]
    assert not row.enabled and row.offer.reason == "Needs 40 tokens"   # Rookie has no tokens
    assert not shop.rows["card_back_royal"].enabled                     # an achievement reward: locked
    assert not shop.rows["card_back_standard"].enabled                  # owned and equipped
    meta.service().grant_tokens(rookie.id, 45)
    shop.refresh()
    _click(app, shop.rows["card_back_crimson"])
    assert meta.get_player(rookie.id).tokens == 5 and "purchased" in shop.message
    assert meta.loadout(rookie.id)["deck"] == "card_back_standard"     # buying does not equip
    _click(app, shop.rows["card_back_crimson"])                         # a second click equips it
    assert app.assets.resolve("card_back") == "card_back_crimson"
    # The Wardrobe only lists owned looks and only switches between them.
    profile = _screen(app, "profile", player_id=rookie.id, tab="wardrobe", slot="deck")
    assert set(profile.rows) == {"card_back_standard", "card_back_crimson"}
    assert profile.collection["deck"] == (2, 7)
    _click(app, profile.rows["card_back_standard"])
    assert app.assets.aliases == {} and "equipped" in profile.message
    assert meta.get_player(rookie.id).tokens == 5                       # no tokens spent here
    _click(app, profile.shop_button)
    assert type(app.scenes.top).__name__ == "MetaShopScene" and app.scenes.top.area == "cosmetics"


def test_preview_follows_the_hovered_look(app) -> None:
    ace = meta.list_slots()[0].player
    profile = _screen(app, "profile", player_id=ace.id, tab="wardrobe", slot="table")
    looks, shown = profile.preview_looks()
    assert shown.id == "table_poker_head" and looks["deck"].id == "card_back_crimson"
    assert "table_midnight" not in profile.rows  # not owned: only in the Shop
    shop = _screen(app, "meta_shop", player_id=ace.id, area="cosmetics", series="core")
    row = shop.rows["table_midnight"]
    shop.list.scroll_into_view(row)
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=row.rect.center, rel=(0, 0), buttons=(0, 0, 0)))
    looks, shown = shop.preview_looks()
    assert shown.id == "table_midnight" and looks["table"].id == "table_midnight"
    app._render()  # noqa: SLF001


def test_achievements_tab_lists_every_achievement_unlocked_first(app) -> None:
    ace = meta.list_slots()[0].player
    profile = _screen(app, "profile", player_id=ace.id, tab="achievements")
    states = [row.state for row in profile.list.children]
    assert len(states) == len(meta.achievements(ace.id))
    unlocked = [s.unlocked for s in states]
    assert unlocked == sorted(unlocked, reverse=True) and unlocked[0]


def test_switching_player_from_profile_returns_home(app) -> None:
    home = _screen(app, "home")
    _click(app, home.badge)
    _click(app, app.scenes.top.switch_button)
    _click(app, app.scenes.top.buttons[(2, "continue")])
    assert app.scenes.top is home and home.player.name == "Rookie"


def test_run_result_shows_unlocks_and_equips_a_rewarded_look(app) -> None:
    from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank

    rookie = meta.list_slots()[1].player
    with meta.service()._db() as db, db:  # noqa: SLF001 - one surrender short of White Flag
        db.execute("INSERT INTO player_stat (player_id, stat_id, total, best) VALUES (?, 'surrenders', 29, 1)",
                   (rookie.id,))
    run = meta.start_run(rookie.id, "normal", seed=1)
    c = run.controller
    c.run.money = 300
    c.place_bet(150)
    c.state = GameState(tuple(Card(Rank(r), "♠") for r in ("K", "Q")), tuple(Card(Rank(r), "♥") for r in ("10", "8")),
                        (Card(Rank("2"), "♣"),), GamePhase.PLAYER_TURN)
    c.stand()
    c.finish_dealer()
    meta.service()._trackers[run.run_id].surrenders = 1  # noqa: SLF001
    result = _screen(app, "run_result", run_id=run.run_id, player_id=rookie.id, controller=c)
    ids = {u.achievement_id for u in result.reward.unlocked}
    assert {"first_win", "white_flag"} <= ids
    equip = result.equip_buttons["white_flag"]
    _click(app, equip)
    assert equip.text == "Equipped" and not equip.enabled
    assert meta.get_player(rookie.id).avatar == "avatar_joker"
    assert app.assets.resolve("avatar") == "avatar_joker"
