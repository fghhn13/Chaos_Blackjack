"""Player GUI flows through agent A's real API installed on a throwaway store."""

import os
from dataclasses import replace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack import meta
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, Rank, GameState, GamePhase
from chaos_blackjack.gui.app import App
from chaos_blackjack.gui.scene import Scene
from chaos_blackjack.gui.settings import GuiSettings
from chaos_blackjack.meta.fake import install_fake


@pytest.fixture
def app(tmp_path):
    svc = install_fake()
    application = App(GuiSettings(asset_dirs=(tmp_path,)), run_config=RunConfig(use_llm=False))
    import chaos_blackjack.gui.scenes

    application.meta_test_service = svc
    yield application
    application.audio.close()
    svc._conn.close()
    meta.use_service(None)
    pygame.quit()


def open_screen(app, name, **params):
    app.scenes.reset(name, **params)
    app.scenes.apply_pending()
    app._render()
    return app.scenes.top


def key(app, code):
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0))
    app.scenes.apply_pending()
    app._render()


def click(app, button):
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        app.scenes.handle_event(pygame.event.Event(kind, pos=button.rect.center, button=1))
    app.scenes.apply_pending()
    app._render()


def player_id():
    return meta.list_slots()[0].player.id


def open_saves(app):
    home = open_screen(app, "home")
    click(app, home.badge)
    return app.scenes.top


def test_slot_create_name_entry_and_play(app):
    select = open_saves(app)
    assert len(select.slots) == 3 and select.slots[2].player is None
    click(app, select.buttons[(3, "create")])
    dialog = app.scenes.top
    app.scenes.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="Jia"))
    assert dialog.value == "Jia"
    key(app, pygame.K_RETURN)
    home = app.scenes.top
    assert type(home).__name__ == "HomeScene" and home.player.name == "Jia"
    assert meta.list_slots()[2].player.name == "Jia"
    click(app, home.badge)
    click(app, app.scenes.top.buttons[(1, "continue")])
    assert app.scenes.top is home and home.player.name == "Ace"


def test_invalid_name_stays_in_dialog_and_cancel_keeps_slot_empty(app):
    select = open_screen(app, "player_select")
    click(app, select.buttons[(3, "create")])
    dialog = app.scenes.top
    key(app, pygame.K_RETURN)
    assert app.scenes.top is dialog and dialog.message
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top.slots[2].player is None


def test_rename_replaces_selected_text(app):
    select = open_screen(app, "player_select")
    click(app, select.buttons[(1, "rename")])
    app.scenes.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="Renamed"))
    key(app, pygame.K_RETURN)
    assert app.scenes.top.slots[0].player.name == "Renamed"


def test_delete_requires_confirmation_and_refreshes_slots(app):
    select = open_screen(app, "player_select")
    click(app, select.buttons[(2, "delete")])
    key(app, pygame.K_ESCAPE)
    assert meta.list_slots()[1].player is not None
    click(app, select.buttons[(2, "delete")])
    key(app, pygame.K_RETURN)
    assert meta.list_slots()[1].player is None
    assert (2, "create") in select.buttons


def test_duplicate_name_submit_creates_only_one_player(app):
    select = open_saves(app)
    click(app, select.buttons[(3, "create")])
    dialog = app.scenes.top
    dialog.value = "Once"
    dialog.submit()
    dialog.submit()
    app.scenes.apply_pending()
    assert meta.list_slots()[2].player.name == "Once"
    assert [type(s).__name__ for s in app.scenes.stack] == ["HomeScene"]


def test_meta_shop_buy_refreshes_cost_tokens_and_levels(app):
    pid = player_id()
    shop = open_screen(app, "meta_shop", player_id=pid)
    offer = next(o for o in shop.offers if o.upgrade_id == "start_money")
    before = meta.get_player(pid)
    click(app, shop.buy_buttons[offer.upgrade_id])
    after = meta.get_player(pid)
    assert after.tokens == before.tokens - offer.next_cost
    assert after.upgrades[offer.upgrade_id] == offer.owned + 1
    assert not shop.buy_buttons[offer.upgrade_id].enabled  # maxed at level three


def test_shop_tabs_consumables_and_rejected_stale_purchase(app):
    pid = player_id()
    shop = open_screen(app, "meta_shop", player_id=pid)
    shop.tab("consumable")
    offer = next(o for o in shop.offers if o.upgrade_id == "start_peek")
    click(app, shop.buy_buttons[offer.upgrade_id])
    assert meta.get_player(pid).upgrades[offer.upgrade_id] == offer.owned + 1
    app.meta_test_service.grant_tokens(pid, -10000)
    shop.buy(offer.upgrade_id)
    assert shop.message and not shop.buy_buttons[offer.upgrade_id].enabled
    app._render()


def test_home_refreshes_after_upgrades_and_settings_keep_navigation(app):
    home = open_screen(app, "home")
    tokens = home.player.tokens
    click(app, home.entries["upgrades"])
    app.scenes.top.tab("consumable")
    click(app, app.scenes.top.buy_buttons["start_peek"])
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is home and home.player.tokens < tokens
    click(app, home.entries["new"])
    assert "start_peek" in app.scenes.top.item_rows
    key(app, pygame.K_ESCAPE)
    click(app, home.settings)
    settings = app.scenes.top
    settings.mute.click()
    assert app.audio.muted
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is home


def test_mode_and_consumable_choices_only_spend_when_run_starts(app):
    pid = player_id()
    hub = open_screen(app, "run_setup", player_id=pid)
    before = meta.get_player(pid)
    hub.choose_mode("chaos")
    hub.toggle_consumable("start_peek")
    assert meta.get_player(pid) == before
    hub.begin_run()
    hub.begin_run()  # queued clicks must not consume a second copy
    app.scenes.apply_pending()
    table = app.scenes.top
    assert type(table).__name__ == "MetaTableScene"
    assert table.controller.config.enable_chaos
    assert table.controller.run.items.count("peek") == 1
    assert meta.get_player(pid).upgrades["start_peek"] == before.upgrades["start_peek"] - 1
    assert sum(r.result is None for r in meta.history(pid)) == 1
    assert meta.resume_run(pid).controller.run.items == table.controller.run.items
    app._render()


def test_started_config_fingerprint_matches_controller_and_checkpoint(app):
    started = meta.start_run(player_id(), "normal")
    assert started.config.balance_hash == started.controller.config.balance_hash
    started.controller.save("fingerprint")
    resumed = meta.resume_run(player_id())
    assert resumed.config.balance_hash == started.config.balance_hash


def test_player_action_checkpoint_survives_gui_shutdown(app):
    pid = player_id()
    started = meta.start_run(pid, "normal")
    table = open_screen(app, "meta_table", started=started, player_id=pid)
    def fixed_round(seed=None, *, inventory_override=None):
        return GameState((Card(Rank("5")), Card(Rank("6"))),
                         (Card(Rank("9")), Card(Rank("7"))), (Card(Rank("2")), Card(Rank("K"))),
                         GamePhase.PLAYER_TURN, inventory=inventory_override or ())
    table.controller.loop.new_round = fixed_round
    table._deal(10)
    table._command("hit")()
    saved_cards = table.controller.view().player_cards
    resumed = meta.resume_run(pid)
    assert resumed.controller.view().player_cards == saved_cards
    assert resumed.controller.view().player_total == 13
    assert meta.history(pid)[0].result is None


def test_long_history_summary_can_be_scrolled_to_the_last_item(app):
    scene = open_screen(app, "history", player_id=player_id())
    scene.selected = replace(scene.selected, summary={
        "items_used": {f"very_long_custom_item_{i}": 1 for i in range(100)}})
    capacity = 222 // app.assets.font(16).get_linesize()
    assert len(scene.detail_lines()) > capacity
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-100))
    assert scene.detail_scroll > 0
    visible = scene.detail_lines()[scene.detail_scroll:scene.detail_scroll + capacity]
    assert "custom item 99" in " ".join(visible)
    app._render()
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=100))
    assert scene.detail_scroll == 0


def test_start_error_keeps_consumable_selection_and_reenables_controls(app, monkeypatch):
    hub = open_screen(app, "run_setup", player_id=player_id())
    hub.toggle_consumable("start_peek")
    def reject(*args, **kwargs):
        raise meta.MetaError("Cannot start this run")
    monkeypatch.setattr(meta, "start_run", reject)
    hub.begin_run()
    assert not hub.starting and not hub.leaving and hub.start_button.enabled
    assert "start_peek" in hub.selected and hub.message == "Cannot start this run"
    app._render()


def test_missing_real_backend_does_not_consume_items_or_create_a_run(app, monkeypatch):
    import chaos_blackjack.ai.gptsapi_llm as relay

    monkeypatch.setattr(relay, "try_create_gptsapi_llm", lambda: None)
    app.run_config = replace(app.run_config, use_llm=True)
    hub = open_screen(app, "run_setup", player_id=player_id())
    hub.toggle_consumable("start_peek")
    before_player, before_runs = meta.get_player(player_id()), meta.history(player_id())
    hub.begin_run()
    assert not hub.starting and "not configured" in hub.message
    assert meta.get_player(player_id()) == before_player
    assert meta.history(player_id()) == before_runs
    app._render()


def test_home_without_unfinished_run_leads_with_new_run(app):
    home = open_screen(app, "home")
    assert home.player.name == "Ace" and "continue" not in home.entries
    assert home.entries["new"].weight == "primary"
    assert list(home.entries) == ["new", "upgrades", "codex", "history"]
    app.running = True
    key(app, pygame.K_ESCAPE)
    assert type(app.scenes.top).__name__ == "ConfirmScene"
    key(app, pygame.K_RETURN)
    assert app.running is False


def test_home_with_unfinished_run_leads_with_continue_and_summary(app):
    pid = player_id()
    started = meta.start_run(pid, "chaos")
    started.controller.save("pending")
    home = open_screen(app, "home")
    assert list(home.entries)[:2] == ["continue", "new"]
    assert home.entries["continue"].weight == "primary" and home.entries["new"].weight == "secondary"
    run = started.controller.run
    assert home.entries["continue"].detail == f"Chaos  ·  Round {max(1, run.round)}  ·  {run.money} chips"


def test_first_launch_start_game_creates_player_and_opens_setup(app):
    for slot in meta.list_slots():
        if slot.player:
            meta.delete_player(slot.player.id)
    home = open_screen(app, "home")
    assert home.player is None and type(home.badge).__name__ == "EmptyBadge"
    assert list(home.entries) == ["start", "upgrades", "codex", "history"]
    assert home.entries["upgrades"].note and home.entries["history"].note
    click(app, home.entries["start"])
    app.scenes.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="Nova"))
    key(app, pygame.K_RETURN)
    setup = app.scenes.top
    assert type(setup).__name__ == "RunSetupScene" and setup.player.name == "Nova"
    assert meta.list_slots()[0].player.name == "Nova"


@pytest.mark.parametrize("target", ["upgrades", "history", "badge"])
def test_player_only_entries_explain_and_point_at_start_game(app, target):
    for slot in meta.list_slots():
        if slot.player:
            meta.delete_player(slot.player.id)
    home = open_screen(app, "home")
    click(app, home.badge if target == "badge" else home.entries[target])
    assert app.scenes.top is home and "Create one with Start game" in home.message
    assert home.point > 0 and home.ui.focus is home.entries["start"]
    key(app, pygame.K_RETURN)  # the pointed-at button is focused, so Enter creates a player
    assert type(app.scenes.top).__name__ == "NameDialog"


def test_home_remembers_choice_and_switching_player_updates_run_info(app):
    pid = player_id()
    meta.start_run(pid, "normal").controller.save("ace")
    rookie = meta.list_slots()[1].player.id
    home = open_screen(app, "home")
    assert "continue" in home.entries
    click(app, home.badge)
    click(app, app.scenes.top.buttons[(2, "continue")])
    assert home.player.id == rookie and "continue" not in home.entries
    assert app.session["player_id"] == rookie
    assert open_screen(app, "home").player.id == rookie  # remembered on return


def test_deleting_current_player_falls_back_to_another(app):
    select = open_saves(app)
    current = app.session["player_id"]
    slot = next(s.slot for s in select.slots if s.player and s.player.id == current)
    click(app, select.buttons[(slot, "delete")])
    key(app, pygame.K_RETURN)
    key(app, pygame.K_ESCAPE)
    home = app.scenes.top
    assert home.player is not None and home.player.id != current


def test_setup_choices_survive_leaving_and_returning(app):
    pid = player_id()
    setup = open_screen(app, "run_setup", player_id=pid)
    setup.choose_mode("chaos")
    setup.toggle_consumable("start_peek")
    again = open_screen(app, "run_setup", player_id=pid)
    assert again.mode_id == "chaos" and again.selected == {"start_peek"}
    assert again.item_rows["start_peek"].check and again.mode_rows["chaos"].selected


def test_setup_keyboard_focus_moves_and_activates(app):
    setup = open_screen(app, "run_setup", player_id=player_id())
    key(app, pygame.K_DOWN)
    assert setup.ui.focus is setup.mode_rows["normal"]
    key(app, pygame.K_DOWN)
    key(app, pygame.K_SPACE)
    assert setup.mode_id == "chaos"


def test_broken_save_hides_continue_with_message(app, monkeypatch):
    pid = player_id()
    meta.start_run(pid, "normal").controller.save("broken")
    home = open_screen(app, "home")
    monkeypatch.setattr(meta, "resume_run", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad save")))
    click(app, home.entries["continue"])
    assert app.scenes.top is home and "could not be restored" in home.message
    assert "continue" not in home.entries and home.entries["new"].weight == "primary"


def test_saved_run_continue_does_not_consume_again(app):
    pid = player_id()
    started = meta.start_run(pid, "normal", consumables=["start_peek"])
    started.controller.save("continued")
    before = meta.get_player(pid).upgrades
    home = open_screen(app, "home")
    click(app, home.entries["continue"])
    assert app.scenes.top.run_id == started.run_id
    assert meta.get_player(pid).upgrades == before


def test_replacing_saved_run_requires_confirmation(app):
    pid = player_id()
    old = meta.start_run(pid, "normal")
    old.controller.save("old")
    hub = open_screen(app, "run_setup", player_id=pid)
    click(app, hub.start_button)
    key(app, pygame.K_ESCAPE)
    assert meta.history(pid)[0].result is None
    click(app, hub.start_button)
    key(app, pygame.K_RETURN)
    assert type(app.scenes.top).__name__ == "MetaTableScene"
    records = {r.id: r for r in meta.history(pid)}
    assert records[old.run_id].result == "abandoned"
    assert records[old.run_id].tokens_earned == 0


def test_table_exit_confirmation_abandons_without_reward(app):
    pid = player_id()
    started = meta.start_run(pid, "normal")
    table = open_screen(app, "meta_table", started=started, player_id=pid)
    before = meta.get_player(pid).tokens
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is table
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_RETURN)
    assert type(app.scenes.top).__name__ == "HomeScene"
    assert meta.history(pid)[0].result == "abandoned"
    assert meta.get_player(pid).tokens == before


@pytest.mark.parametrize("kind", ["victory", "defeat"])
def test_finished_table_routes_to_reward_once_and_back_to_hub(app, kind):
    pid = player_id()
    started = meta.start_run(pid, "normal")
    table = open_screen(app, "meta_table", started=started, player_id=pid)
    c = table.controller
    from chaos_blackjack.logic.run_end_policy import RunEndResult
    c.run = replace(c.run, money=400 if kind == "victory" else 1, round=20)
    c.run_end = RunEndResult(kind, "Finished")
    c.phase = TablePhase.RUN_OVER
    table._after_command()
    before = meta.get_player(pid).tokens
    table.update(3)
    table.update(3)
    app.scenes.apply_pending()
    result = app.scenes.top
    assert type(result).__name__ == "RunResultScene"
    assert result.reward.result == kind
    assert sum(value for _, value in result.reward.breakdown) == result.reward.tokens
    assert meta.get_player(pid).tokens == before + result.reward.tokens
    app._render()
    result.settle()
    assert meta.get_player(pid).tokens == before + result.reward.tokens
    key(app, pygame.K_RETURN)
    assert type(app.scenes.top).__name__ == "HomeScene"
    assert meta.history(pid)[0].result == kind


def test_result_error_offers_retry_and_cannot_leave_before_settlement(app, monkeypatch):
    started = meta.start_run(player_id(), "normal")
    def reject(*args):
        raise meta.MetaError("The run is not over yet")
    monkeypatch.setattr(meta, "finish_run", reject)
    scene = open_screen(app, "run_result", run_id=started.run_id,
                        player_id=player_id(), controller=started.controller)
    assert scene.reward is None and not scene.back.enabled
    assert "not over" in scene.message
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is scene


def test_history_detail_is_from_api_and_empty_history_renders(app):
    history = open_screen(app, "history", player_id=player_id())
    assert len(history.records) == 3
    click(app, history.record_buttons[history.records[1].id])
    assert history.selected.result == "victory"
    assert history.selected.summary["rules_seen"] == {"great_crash": 2}
    rookie = meta.list_slots()[1].player.id
    empty = open_screen(app, "history", player_id=rookie)
    assert empty.selected is None and not empty.record_buttons


def test_history_pagination_includes_newer_and_older_records(app):
    pid = player_id()
    for _ in range(8):
        meta.abandon_run(meta.start_run(pid, "normal").run_id)
    scene = open_screen(app, "history", player_id=pid)
    first = set(scene.record_buttons)
    scene.turn_page(1)
    assert len(scene.record_buttons) == 4 and first.isdisjoint(scene.record_buttons)
    app._render()


def test_codex_handoff_is_available_when_c_registers_scene(app, monkeypatch):
    class Codex(Scene):
        def on_enter(self, player_id, config):
            self.player_id, self.config = player_id, config
    monkeypatch.setitem(app.scenes.registry, "codex", Codex)
    home = open_screen(app, "home")
    click(app, home.entries["codex"])
    assert app.scenes.top.player_id == player_id()
    assert app.scenes.top.config == app.run_config


def test_invalid_player_setup_shows_error_and_can_return(app):
    home = open_screen(app, "home")
    app.scenes.push("run_setup", player_id=99999)
    app.scenes.apply_pending()
    setup = app.scenes.top
    assert setup.message
    app._render()
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is home
