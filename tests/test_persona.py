"""AI personas: validation, asset lookup and how the table's Chaos panel uses them."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from types import SimpleNamespace  # noqa: E402

from chaos_blackjack.app.notices import Notice, NoticeKind  # noqa: E402
from chaos_blackjack.content.ai_profile import Persona, persona_image  # noqa: E402
from chaos_blackjack.gui.assets import AssetManager  # noqa: E402
from chaos_blackjack.gui.components.chaos_panel import BUST_LINE, ChaosPanel  # noqa: E402


@pytest.fixture
def persona(tmp_path):
    files = {}
    for name in ("neutral", "smirk", "frown"):
        surf = pygame.Surface((8, 8))
        files[name] = tmp_path / f"{name}.png"
        pygame.image.save(surf, str(files[name]))
    return Persona(
        id="test_dealer", name="Test Dealer", portraits=files,
        moods={"rule_applied": "smirk", "outcome_player": "frown", "player_bust": "smirk"},
        lines={"rule_applied": ("Now {rule}.", "Again {rule}."), "outcome_player": ("Hm.",),
               "player_bust": ("Too far.",), "idle": ("Waiting.",)},
    )


def notice(kind, **data):
    return Notice(kind, "", data)


def test_persona_validation(tmp_path):
    with pytest.raises(ValueError, match="default expression"):
        Persona(id="x", name="X", portraits={})
    path = tmp_path / "a.png"
    with pytest.raises(ValueError, match="unknown events"):
        Persona(id="x", name="X", portraits={"neutral": path}, lines={"nonsense": ("a",)})
    with pytest.raises(ValueError, match="without portraits"):
        Persona(id="x", name="X", portraits={"neutral": path}, moods={"poke": "grin"})


def test_assets_find_persona_portraits(persona, tmp_path):
    assets = AssetManager((tmp_path / "empty",))
    assert persona_image("test_dealer_smirk") == persona.portraits["smirk"]
    assert assets.has_file("test_dealer_smirk") and assets.source("test_dealer_smirk") == "file"
    assert assets.image("test_dealer_smirk").get_size() == (8, 8)
    assert persona.asset_id("missing") == "test_dealer_neutral"


def test_panel_uses_persona_moods_lines_and_keeps_the_bust_remark(persona, tmp_path):
    panel = ChaosPanel(AssetManager((tmp_path / "empty",)), (0, 0, 240, 640), persona=persona)
    panel.chaos_enabled = True
    assert panel.mood == "neutral" and panel._face() == "test_dealer_neutral"
    panel.react(notice(NoticeKind.RULE_MODIFIER_APPLIED, rule_id="suit_power"))
    assert panel.mood == "smirk" and panel.speech == "Now Suit Power."
    panel.react(notice(NoticeKind.RULE_MODIFIER_APPLIED, rule_id="great_crash"))
    assert panel.speech == "Again Great Crash."  # lines rotate
    panel.react(notice(NoticeKind.ROUND_STARTED))
    panel.react(notice(NoticeKind.PLAYER_BUST))
    panel.react(notice(NoticeKind.ROUND_SETTLED, result=SimpleNamespace(outcome="dealer")))
    assert panel.speech == "Too far."
    panel.react(notice(NoticeKind.ROUND_STARTED))
    panel.react(notice(NoticeKind.ROUND_SETTLED, result=SimpleNamespace(outcome="player")))
    assert panel.mood == "frown" and panel.speech == "Hm."
    panel.react(notice(NoticeKind.CHAOS_NARRATION, text="As you wish."))
    assert panel.speech == "As you wish."



def test_panel_speaks_a_tables_own_events(tmp_path):
    from chaos_blackjack.content.builtin_persona import host_persona

    j54 = host_persona("j54")
    panel = ChaosPanel(AssetManager((tmp_path / "empty",)), (0, 0, 240, 640), persona=j54)
    panel.chaos_enabled = True
    panel.react(notice(NoticeKind.TABLE_EVENT, effect="condition"))
    assert panel.speech in j54.lines["table_condition"] and panel.mood == j54.moods["table_condition"]
    panel.react(notice(NoticeKind.TABLE_EVENT, effect="release"))
    assert panel.speech in j54.lines["table_release"]
    before = panel.speech
    panel.react(notice(NoticeKind.TABLE_EVENT, effect="entropy"))  # no lines for it: the speech stays
    assert panel.speech == before


def test_panel_without_persona_is_unchanged(tmp_path):
    panel = ChaosPanel(AssetManager((tmp_path / "empty",)), (0, 0, 240, 640))
    panel.chaos_enabled = True
    panel.react(notice(NoticeKind.PLAYER_BUST))
    assert panel.mood == "laugh" and panel.speech == BUST_LINE and panel._face().startswith("chaos_")
