"""Onboarding in the GUI: the practice prompt, the practice table, the chart and table silhouettes."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack import meta
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.gui.app import App
from chaos_blackjack.gui.settings import GuiSettings
from chaos_blackjack.meta.fake import install_fake
from chaos_blackjack.meta.onboarding import TUTORIAL
from chaos_blackjack.tutorial.lessons import LESSONS


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_TUTORIAL", "1")
    svc = install_fake(demo=False)
    application = App(GuiSettings(asset_dirs=(tmp_path,)), run_config=RunConfig(use_llm=False))
    import chaos_blackjack.gui.scenes  # noqa: F401

    yield application
    application.audio.close()
    svc._conn.close()
    meta.use_service(None)
    pygame.quit()


def settle(app, frames=1, dt=0.0):
    for _ in range(frames):
        app.scenes.update(dt)
        app.scenes.apply_pending()
    app._render()


def key(app, code):
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0))
    app.scenes.apply_pending()
    app._render()


def finish_dialogs(app, scene):
    while scene.dialog() is not None:
        scene.dialog().skip()
        settle(app)


def name(app):
    return type(app.scenes.top).__name__


def test_first_visit_offers_practice_and_skip_finishes_the_tutorial(app):
    player = meta.create_player(1, "New")
    app.scenes.reset("run_setup", player_id=player.id)
    settle(app, 2)
    assert name(app) == "ConfirmScene"
    key(app, pygame.K_ESCAPE)                       # Skip
    assert name(app) == "RunSetupScene"
    assert TUTORIAL in meta.milestones(player.id)
    setup = app.scenes.top
    rows = {o.mode.id: setup.is_silhouette(o) for o in setup.options}
    assert rows == {"normal": False, "chaos": True}   # J-54 is not even a silhouette yet
    setup.choose_mode("chaos")
    settle(app)
    assert setup.mode_id == "chaos" and not setup.start_button.enabled


def test_practice_hands_run_to_the_chart_and_finish(app):
    player = meta.create_player(1, "New")
    app.scenes.reset("run_setup", player_id=player.id)
    settle(app, 2)
    key(app, pygame.K_RETURN)                       # Practice
    table = app.scenes.top
    assert name(app) == "TutorialTableScene" and table.dialog() is not None
    for _ in range(400):
        if name(app) != "TutorialTableScene":
            break
        finish_dialogs(app, table)
        v = table.view
        lesson = table.table.lesson
        if v.phase == TablePhase.BETTING:
            table._deal(10)
        elif v.phase == TablePhase.PLAYER_TURN:
            action = lesson.action if len(v.player_cards) == 2 else lesson.then
            table.action_buttons[action or "stand"].on_click()
        elif v.phase == TablePhase.ROUND_OVER:
            table.next_button.on_click()
        table.fx.skip() if hasattr(table.fx, "skip") else None
        settle(app, dt=2.0)
    assert name(app) == "StrategyChartScene"
    chart = app.scenes.top
    assert chart.dialog is not None
    chart.dialog.skip()
    key(app, pygame.K_ESCAPE)                       # Done
    assert name(app) == "RunSetupScene"
    assert TUTORIAL in meta.milestones(player.id)


def test_the_chart_opens_from_the_collection(app):
    app.scenes.reset("codex")
    settle(app)
    app.scenes.top.chart.on_click()
    settle(app)
    assert name(app) == "StrategyChartScene" and app.scenes.top.dialog is None
    key(app, pygame.K_ESCAPE)
    assert name(app) == "CodexScene"


def test_lessons_cover_each_button_once():
    taught = [lesson.action for lesson in LESSONS if lesson.action]
    assert sorted(taught) == ["double", "hit", "stand", "surrender"]


def test_first_visit_to_poker_head_explains_builds_once(app):
    from chaos_blackjack.meta.onboarding import CLASSIC_MAX_WIN, PH_INTRO_BUILD
    from chaos_blackjack.tutorial.lessons import PH_INTRO_BUILD as BUILD_LINES

    player = meta.create_player(1, "New")
    for m in (TUTORIAL, CLASSIC_MAX_WIN):
        meta.reach(player.id, m)
    started = meta.start_run(player.id, "chaos", stake=400)
    app.scenes.reset("meta_table", started=started, player_id=player.id, intro=True)
    settle(app)
    texts = app.scenes.top.intro.lines
    assert BUILD_LINES[0][1] in texts
    assert PH_INTRO_BUILD in meta.milestones(player.id)
    assert app.scenes.top.explain_rules


def test_a_new_players_classic_greeting_mentions_the_bet_cap(app):
    player = meta.create_player(1, "New")
    meta.reach(player.id, TUTORIAL)
    started = meta.start_run(player.id, "normal", stake=40)
    app.scenes.reset("meta_table", started=started, player_id=player.id, intro=True)
    settle(app)
    assert any("quarter of your cash" in line for line in app.scenes.top.intro.lines)


def test_poker_head_speaks_when_he_tops_up_a_broke_vault(app):
    from chaos_blackjack.tutorial.lessons import FIRST_RELIEF, RELIEF

    player = meta.create_player(1, "New")
    meta.reach(player.id, TUTORIAL)
    seen = []
    for _ in range(2):
        started = meta.start_run(player.id, "normal", stake=40)
        with meta.service()._db() as db, db:
            db.execute("UPDATE player SET tokens = 0 WHERE id = ?", (player.id,))
        c = started.controller
        c.run.money = 0
        c.check_terminal()
        app.scenes.reset("run_result", run_id=started.run_id, player_id=player.id, controller=c)
        settle(app)
        seen.append(app.scenes.top.dialog.lines)
    assert seen[0] == [text for _, text in FIRST_RELIEF]
    assert seen[1] == [text for _, text in RELIEF]


def test_a_new_players_collection_shows_undiscovered_entries_and_a_silhouette_tab(app):
    player = meta.create_player(1, "New")
    app.scenes.reset("codex", player_id=player.id)
    settle(app)
    codex = app.scenes.top
    assert [s.id for s in codex.sections] == ["core", "poker_head"]       # J-54 is not shown yet
    assert codex.tabs["poker_head"].text == "???"
    items = [e for e in codex.entries if e.kind == "item"]
    assert items and not any(codex.known(e) for e in items)
    codex._select_entry(items[0])
    assert not codex.open_detail.enabled and "shop shelf" in codex.reference
    assert codex.known(next(e for e in codex.entries if e.kind == "mode"))
    codex._select("poker_head")
    settle(app)
    assert not codex.about.visible and "top stake" in codex.reference
