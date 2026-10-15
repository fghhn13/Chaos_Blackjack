"""The table log wraps long messages instead of cutting them (a result word must never hide behind "…")."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.gui.assets import AssetManager
from chaos_blackjack.gui.components.hud import EventFeed
from chaos_blackjack.gui import theme


@pytest.fixture
def assets(tmp_path):
    pygame.init()
    yield AssetManager((tmp_path,))
    pygame.quit()


def test_the_newest_message_shows_in_full_on_wrapped_rows(assets):
    feed = EventFeed(assets, (0, 0), max_lines=4, max_width=160, align_top=True)
    feed.push("Dealer stands at 18.")
    feed.push("BUST if you hit (Risk Pointer). Poker Head smiles at your cards.")
    rows = feed.rows(assets.font(theme.FONT_SMALL))
    newest = [text for text, line in rows if line is feed.lines[-1]]
    assert len(newest) > 1 and " ".join(newest) == feed.lines[-1].text   # wrapped, nothing cut
    assert len(rows) <= 4


def test_older_messages_leave_whole_when_rows_run_out(assets):
    feed = EventFeed(assets, (0, 0), max_lines=3, max_width=160, align_top=True)
    feed.push("An old line that is long enough to need two rows here.")
    feed.push("Next card: 10 (Card Lens). It will not bust a hard 11.")
    rows = feed.rows(assets.font(theme.FONT_SMALL))
    assert {line.text for _, line in rows} == {feed.lines[-1].text}       # no half of the old line
    assert len(rows) <= 3
