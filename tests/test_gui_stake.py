"""The stake slider and the run setup's stake (docs/design/META_PROGRESSION.md "Chip vault")."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack import meta
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.gui.app import App
from chaos_blackjack.gui.settings import GuiSettings
from chaos_blackjack.gui.widgets import Slider
from chaos_blackjack.meta.fake import install_fake


@pytest.fixture
def app(tmp_path):
    svc = install_fake()
    application = App(GuiSettings(asset_dirs=(tmp_path,)), run_config=RunConfig(use_llm=False))
    import chaos_blackjack.gui.scenes  # noqa: F401

    application.meta_test_service = svc
    yield application
    application.audio.close()
    svc._conn.close()
    meta.use_service(None)
    pygame.quit()


def _mouse(widget, kind, x, y=None):
    y = widget.rect.centery if y is None else y
    if kind == pygame.MOUSEMOTION:
        return widget.handle_event(pygame.event.Event(kind, pos=(x, y), rel=(0, 0), buttons=(1, 0, 0)))
    return widget.handle_event(pygame.event.Event(kind, pos=(x, y), button=1))


def _setup(app, player_id, mode):
    app.session.setdefault("setup", {}).setdefault(player_id, {"mode": mode, "bring": set()})["mode"] = mode
    app.scenes.reset("run_setup", player_id=player_id)
    app.scenes.apply_pending()
    app._render()
    return app.scenes.top


# --- the widget ------------------------------------------------------------------------------------


def test_slider_drags_jumps_and_snaps(app):
    seen = []
    s = Slider(app.assets, (100, 100, 232, 36), 400, 1000, 400, seen.append, step=10)
    left, right = s._track()  # noqa: SLF001
    assert _mouse(s, pygame.MOUSEBUTTONDOWN, right)          # press on the track: jump there
    assert s.value == 1000 and s.dragging
    _mouse(s, pygame.MOUSEMOTION, (left + right) // 2)       # drag to the middle
    assert s.value == 700
    _mouse(s, pygame.MOUSEBUTTONUP, (left + right) // 2)
    assert not s.dragging and seen == [1000, 700]
    _mouse(s, pygame.MOUSEMOTION, right)                     # no button held: nothing changes
    assert s.value == 700


def test_slider_keys_move_by_steps_and_reach_both_ends(app):
    s = Slider(app.assets, (0, 0, 300, 36), 40, 95, 40, step=10)
    s.focused = True
    key = lambda k: s.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0))
    key(pygame.K_RIGHT)
    assert s.value == 50
    key(pygame.K_END)
    assert s.value == 95                                     # the top is reachable off the grid
    key(pygame.K_LEFT)
    assert s.value == 90
    key(pygame.K_PAGEDOWN)
    assert s.value == 40
    s.enabled = False
    assert not _mouse(s, pygame.MOUSEBUTTONDOWN, s.rect.right)


# --- the run setup -----------------------------------------------------------------------------------


def test_the_chosen_stake_leaves_the_vault_when_the_run_starts(app):
    pid = meta.list_slots()[0].player.id
    vault = meta.get_player(pid).chips
    setup = _setup(app, pid, "chaos")
    assert setup.stake_bounds == (400, 1000) and setup.stake == 400
    setup.stake_slider.set_value(650)
    assert setup.stake == 650 and "Full Haul from 2600" in setup.stake_goal(setup.stake)
    assert meta.get_player(pid).chips == vault               # nothing spent yet
    setup.start()
    app.scenes.apply_pending()
    assert type(app.scenes.top).__name__ == "MetaTableScene"
    assert app.scenes.top.controller.run.money == 650 and meta.get_player(pid).chips == vault - 650


def test_a_vault_below_the_table_s_minimum_cannot_start_and_a_broke_one_gets_relief(app):
    rid = meta.list_slots()[1].player.id
    app.meta_test_service.grant_tokens(rid, -meta.get_player(rid).chips)
    setup = _setup(app, rid, "chaos")
    assert meta.get_player(rid).chips == 40 and "40 chips" in setup.relief_note
    assert setup.stake_bounds == (400, 40) and not setup.start_button.enabled
    assert not setup.stake_slider.visible
    setup.choose_mode("normal")
    assert setup.start_button.enabled and setup.stake == 40


def test_a_free_table_has_no_slider(app):
    pid = meta.list_slots()[0].player.id
    setup = _setup(app, pid, "j54")
    assert setup.stake_bounds is None and setup.stake_slider is None and setup.start_button.enabled


def test_the_insurance_toggle_follows_the_stake_and_is_bought_with_the_run(app):
    pid = meta.list_slots()[0].player.id
    meta.achievements(pid)                                    # settle the demo history's achievements first
    app.meta_test_service.grant_tokens(pid, 1020 - meta.get_player(pid).chips)
    vault = meta.get_player(pid).chips
    setup = _setup(app, pid, "chaos")
    setup.stake_slider.set_value(500)
    assert setup.insure_toggle.text == "Insure this run  ·  30 chips" and not setup.insured
    setup.insure_toggle.click()
    assert setup.insured and setup.insure_toggle.text == "Insured  ·  30 chips"
    setup.stake_slider.set_value(1000)                        # 1000 + 60 is more than this vault
    assert not setup.insure_toggle.enabled and not setup.insured
    setup.stake_slider.set_value(500)
    setup.insure_toggle.click()
    setup.start()
    app.scenes.apply_pending()
    assert meta.get_player(pid).chips == vault - 530


def test_the_profile_shows_the_membership_badge_and_progress(app):
    pid = meta.list_slots()[0].player.id
    with app.meta_test_service._db() as db, db:  # noqa: SLF001
        db.execute("UPDATE player SET lifetime_spend = 3540 WHERE id = ?", (pid,))
    app.scenes.reset("profile", player_id=pid)
    app.scenes.apply_pending()
    app._render()
    member = app.scenes.top.member
    assert (member.level, member.name) == (3, "Patron")
    from chaos_blackjack.gui.assets import AssetManager
    from chaos_blackjack.gui.settings import PROJECT_ROOT

    shipped = AssetManager((PROJECT_ROOT / "assets",))
    assert all(shipped.source(f"member_{level}") == "file" for level in range(1, 6))   # the drawn badges ship
