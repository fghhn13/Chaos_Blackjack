"""J-54's first visit (docs/design/TUTORIAL.md section 8): four milestones explained once each inside the first
run, the meter hint, the highlights, and nothing for unguided players."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from dataclasses import replace

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.parts import PartContext, build_part
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.app.widgets import ListWidget
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.j54 import onboarding
from chaos_blackjack.j54.table import CUT, RELEASE
from chaos_blackjack.meta.onboarding import (
    ALL, J54_INTRO_CONDITION, J54_INTRO_FIRMWARE, J54_INTRO_RELEASE, J54_INTRO_TABLE,
)
from chaos_blackjack.modes import get_mode


def _config(seed: int = 1, **settings) -> RunConfig:
    cfg = get_mode("j54").apply(RunConfig.from_balance(default_balance(), seed=seed))
    return replace(cfg, mode_settings={**cfg.mode_settings, **{f"j54.{k}": v for k, v in settings.items()}})


def _controller(seed: int = 1, **settings) -> GameController:
    return GameController(_config(seed, **settings), save_fn=lambda d, n: n)


def _play_round(c: GameController) -> None:
    """Bet the minimum on a fixed 19 against a 17 and settle; back to betting."""
    def fixed(seed=None, *, inventory_override=None, cards=None, ordered_cards=None):
        return GameState((Card(Rank("10"), "♠"), Card(Rank("9"), "♠")), (Card(Rank("10"), "♥"), Card(Rank("7"), "♦")),
                         (), GamePhase.PLAYER_TURN, inventory=inventory_override or ())

    c.loop.new_round = fixed  # type: ignore[method-assign]
    c.place_bet(5)
    if c.phase == TablePhase.PLAYER_TURN:
        c.stand()
    c.finish_dealer()
    c.next_round()


def _milestones(c: GameController, guided: bool = True) -> list[str]:
    return [m for m, _ in c.table.onboarding(guided)]


# ------------------------------------------------------------------ the moments


def test_the_milestones_are_onboarding_milestones() -> None:
    assert set(onboarding.MILESTONES) == {J54_INTRO_TABLE, J54_INTRO_FIRMWARE, J54_INTRO_CONDITION, J54_INTRO_RELEASE}
    assert set(onboarding.MILESTONES) <= set(ALL)


def test_the_table_and_firmware_explanations_come_at_the_start_once() -> None:
    c = _controller()
    assert c.choice is not None and c.choice.kind == "firmware"
    due = c.table.onboarding(True)
    assert [m for m, _ in due] == [J54_INTRO_TABLE, J54_INTRO_FIRMWARE]
    table, firmware = (beats for _, beats in due)
    assert all(b.focus == ("j54.deck",) for b in table) and all(not b.focus for b in firmware)
    assert "+2 every round, 8 at most" in " ".join(b.text for b in table)  # the profile's numbers
    assert c.table.onboarding(True) == ()


def test_an_unguided_player_gets_nothing() -> None:
    c = _controller()
    assert c.table.onboarding(False) == ()
    c.choose("none")
    for _ in range(6):
        _play_round(c)
        assert c.table.onboarding(False) == ()
        assert c.view().table_public.hint is None


def test_the_condition_explanation_comes_with_the_first_announcement() -> None:
    c = _controller()
    c.choose("none")
    c.table.onboarding(True)
    announced = []
    for _ in range(10):
        due = _milestones(c)
        if c.table.announcement:
            announced.append(c.run.round)
        assert (J54_INTRO_CONDITION in due) == (len(announced) == 1 and announced[0] == c.run.round)
        c.table.compute = 0  # keep Release out of reach
        _play_round(c)
    assert len(announced) > 1  # later announcements explain nothing


def test_the_release_explanation_comes_when_release_is_affordable() -> None:
    c = _controller()
    c.choose("none")
    c.table.onboarding(True)
    rounds = []
    for _ in range(4):
        if J54_INTRO_RELEASE in _milestones(c):
            rounds.append(c.run.round)
            assert c.table.compute >= 6 and c.view().move(RELEASE).enabled
        _play_round(c)
    assert rounds == [3]  # 2, 4, 6 compute: affordable from round 3, explained once


def test_spending_every_round_never_reaches_the_release_explanation() -> None:
    c = _controller()
    c.choose("none")
    c.table.onboarding(True)
    for _ in range(6):
        while c.view().move(CUT).enabled:
            c.perform(CUT, next(g for g, n in c.table.group_counts().items() if n))
        assert J54_INTRO_RELEASE not in _milestones(c)
        _play_round(c)


def test_a_restored_run_does_not_cue_the_start_again() -> None:
    c = _controller()
    c.table.onboarding(True)
    data = c.save("x")
    loaded = GameController.from_save(RunSaveData.from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert loaded.table.onboarding(True) == ()


# ------------------------------------------------------------------ the meter hint


def _hint_widgets(c: GameController) -> list:
    widgets = build_part("j54.meter", PartContext(c, c.view()), "compact")
    return [w for w in widgets if isinstance(w, ListWidget)]


def test_the_meter_hint_shows_once_per_run_for_a_guided_player() -> None:
    c = _controller(bands="20:10,40:20,60:30")  # a fresh deck (about 44 %) is in the second band
    c.choose("none")
    assert c.view().table_public.hint is None  # nobody has said the player is guided yet
    c.table.onboarding(True)
    snap = c.view().table_public
    assert snap.hint == f"The meter says 20% of the bankroll: {snap.band['suggested']} chips."
    hint = _hint_widgets(c)
    assert hint and hint[0].entries[0].title == "Band two reached"
    c.place_bet(5)
    c.table.onboarding(True)
    assert c.view().table_public.hint is None  # betting only
    c.stand() if c.phase == TablePhase.PLAYER_TURN else None
    c.finish_dealer()
    c.next_round()
    c.table.onboarding(True)
    assert c.view().table_public.hint is None and not _hint_widgets(c)  # once per run


def test_the_meter_hint_waits_for_the_second_band_and_survives_a_save() -> None:
    c = _controller(bands="20:10,90:20")
    c.choose("none")
    c.table.onboarding(True)
    assert c.view().table_public.hint is None and c.table.guide.hint_round is None
    c = _controller(bands="20:10,40:20")
    c.choose("none")
    c.table.onboarding(True)
    data = c.save("x")
    loaded = GameController.from_save(RunSaveData.from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert loaded.table.guide.hint_round == 1
    loaded.table.onboarding(True)
    assert loaded.view().table_public.hint == c.view().table_public.hint


# ------------------------------------------------------------------ the lines


def test_every_milestone_has_three_or_four_beats_in_j54s_voice() -> None:
    from chaos_blackjack.content.builtin_persona import host_persona
    from chaos_blackjack.content.host_script import host_onboarding

    expressions = set(host_persona("j54").portraits)
    c = _controller()
    for milestone in onboarding.MILESTONES:
        assert 3 <= len(host_onboarding("j54", milestone)) <= 4
        beats = onboarding.beats(c.table, milestone)
        assert all(b.mood in expressions and b.text and "{" not in b.text for b in beats)
        assert all(b.focus == onboarding.FOCUS.get(milestone, ()) for b in beats)
    assert host_onboarding("poker_head", J54_INTRO_TABLE) == []


# ------------------------------------------------------------------ the GUI


pygame = pytest.importorskip("pygame")


@pytest.fixture
def app(tmp_path, monkeypatch):
    from chaos_blackjack import meta
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    from chaos_blackjack.meta.fake import install_fake

    monkeypatch.setenv("CHAOS_TUTORIAL", "1")
    svc = install_fake(demo=False)
    application = App(GuiSettings(asset_dirs=(tmp_path,)), run_config=RunConfig(use_llm=False))
    import chaos_blackjack.gui.scenes  # noqa: F401

    yield application
    application.audio.close()
    svc._conn.close()
    meta.use_service(None)
    pygame.quit()


def _settle(app, frames=1):
    for _ in range(frames):
        app.scenes.update(0.0)
        app.scenes.apply_pending()
    app._render()


def _key(app, code):
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0))
    app.scenes.apply_pending()
    app._render()


def _player(guided: bool):
    from chaos_blackjack import meta
    from chaos_blackjack.meta.onboarding import CLASSIC_MAX_WIN, POKER_HEAD_WIN, TUTORIAL

    os.environ["CHAOS_TUTORIAL"] = "1" if guided else "0"
    try:
        player = meta.create_player(1 if guided else 2, "New" if guided else "Old")
    finally:
        os.environ["CHAOS_TUTORIAL"] = "1"
    for m in (TUTORIAL, CLASSIC_MAX_WIN, POKER_HEAD_WIN):
        meta.reach(player.id, m)
    return player


def _open(app, player, *, intro=True):
    from chaos_blackjack import meta

    started = meta.start_run(player.id, "j54", stake=100)
    app.scenes.reset("meta_table", started=started, player_id=player.id, intro=intro)
    _settle(app)
    return app.scenes.top


def _texts(milestone):
    from chaos_blackjack.content.host_script import host_onboarding

    return [b.text for b in host_onboarding("j54", milestone)]


def test_a_guided_first_visit_explains_the_table_and_firmware_before_the_choice(app):
    from chaos_blackjack import meta

    player = _player(True)
    scene = _open(app, player)
    lines = scene.intro.lines
    first = lines.index(next(t for t in lines if t.startswith("Orientation protocol")))
    assert len(lines[first:]) == 7 and lines[-1] == _texts(J54_INTRO_FIRMWARE)[-1]
    assert {J54_INTRO_TABLE, J54_INTRO_FIRMWARE} <= meta.milestones(player.id)
    scene.intro.index = first
    assert scene.dialog().focus == ("j54.deck",) and scene.focus_rects(scene.dialog().focus)
    _key(app, pygame.K_ESCAPE)                       # Esc skips the rest
    assert scene.dialog() is None
    _settle(app)
    assert type(app.scenes.top).__name__ == "ChoiceScene"
    # The next run says none of it again.
    again = _open(app, player)
    assert not any(t.startswith("Orientation protocol") for t in again.intro.lines)


def test_an_unguided_player_hears_only_the_greeting(app):
    from chaos_blackjack import meta

    player = _player(False)
    scene = _open(app, player)
    assert not scene.guided
    assert not any(t in scene.intro.lines for m in onboarding.MILESTONES for t in _texts(m))
    scene.intro.skip()
    scene.controller.choose("none")
    for _ in range(6):
        _play_round(scene.controller)
        scene._after_command()
        _settle(app)
        assert scene.dialog() is None and scene.view.table_public.hint is None


def test_later_explanations_wait_for_their_moment_and_light_up_their_element(app):
    from chaos_blackjack import meta

    player = _player(True)
    scene = _open(app, player)
    scene.intro.skip()
    scene.controller.choose("none")
    scene._after_command()
    app.scenes.reset("meta_table", started=meta.resume_run(player.id), player_id=player.id)
    _settle(app)
    scene = app.scenes.top
    assert scene.dialog() is None  # a resumed run repeats nothing
    c = scene.controller
    seen = {}
    for _ in range(8):
        while scene.dialog() is not None:  # step through the beats with Enter
            beat = scene.dialog().beats[scene.dialog().index]
            for m in (J54_INTRO_CONDITION, J54_INTRO_RELEASE):
                if beat.text == onboarding.beats(c.table, m)[0].text:
                    seen[m] = c.run.round
                    assert scene.dialog().focus == onboarding.FOCUS[m]
                    assert len(scene.focus_rects(onboarding.FOCUS[m])) == len(onboarding.FOCUS[m])
            _key(app, pygame.K_RETURN)
        _play_round(c)
        scene._after_command()
        _settle(app)
    assert set(seen) == {J54_INTRO_CONDITION, J54_INTRO_RELEASE}
    assert {J54_INTRO_CONDITION, J54_INTRO_RELEASE} <= meta.milestones(player.id)


# ------------------------------------------------------------------ polish: suits in GUI text


def test_gui_text_spells_suits_the_fonts_cannot_draw() -> None:
    from chaos_blackjack.app.notices import Notice, NoticeKind
    from chaos_blackjack.gui.texts import notice_line, spell_suits

    assert spell_suits("Cut 10 red: 10♥, 10♦ removed") == "Cut 10 red: 10 of hearts, 10 of diamonds removed"
    line = notice_line(Notice(NoticeKind.TABLE_EVENT, "Cut 2 black: 2♠, 2♣ removed (1 compute left)."))
    assert line[0] == "Cut 2 black: 2 of spades, 2 of clubs removed (1 compute left)."
    c = _controller()
    c.choose("none")
    c.perform(CUT, "5r")
    pile = build_part("j54.program", PartContext(c, c.view()), "full")[-1]
    assert [e.title for e in pile.entries] == ["5h", "5d"] or [e.title for e in pile.entries] == ["5d", "5h"]
    assert all(e.tooltip in ("5 of hearts", "5 of diamonds") and e.tone == "bad" for e in pile.entries)


def test_a_table_that_sells_nothing_has_no_shop_button_and_no_buying(app) -> None:
    from chaos_blackjack.agent import AgentSession
    from chaos_blackjack.app.view import Action

    scene = _open(app, _player(True))
    scene.intro.skip()
    scene.controller.choose("none")
    scene._after_command()
    _settle(app)
    v = scene.view
    assert not v.has_shop and not v.can(Action.BUY) and not v.can(Action.REROLL)
    buttons = scene.buttons_block
    assert not buttons.shop.visible and buttons.panel.rect.w == buttons.rect.w
    _key(app, pygame.K_b)                            # the hotkey opens nothing either
    assert type(app.scenes.top).__name__ == "MetaTableScene"
    obs = AgentSession.new(seed=3, mode="j54").execute({"cmd": "choose", "option": "none"})["obs"]
    assert obs["legal_actions"] == ["bet", "perform"] and obs["shop"] is None
    assert obs["hint"].endswith("(see obs.table_actions).")
    classic = GameController(RunConfig.from_balance(default_balance(), seed=1)).view()
    assert classic.has_shop and classic.can(Action.BUY)
