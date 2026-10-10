"""Audio policy is tested without pygame, wall-clock sleeps or a device."""

import random
import shutil
from types import SimpleNamespace

import pytest

from chaos_blackjack.app.notices import Notice, NoticeKind as N
from chaos_blackjack.audio import AudioManager
from chaos_blackjack.audio.catalog import ASSET_ROOT, validate_assets
from chaos_blackjack.audio.__main__ import main


class RecordingBackend:
    available = True

    def __init__(self):
        self.clips = []
        self.volumes = []
        self.stops = 0
        self.closed = False

    def play(self, path, gain):
        self.clips.append((path.name, gain))
        return True

    def set_volume(self, volume):
        self.volumes.append(volume)

    def stop(self):
        self.stops += 1

    def close(self):
        self.closed = True


def test_assets_and_offline_cli(capsys):
    report = validate_assets()
    assert report["files"] == 54 and report["license"] == "CC0-1.0"
    assert set(report["cues"]) == {"deal", "chips", "win", "lose", "chaos"}
    assert main(["validate"]) == 0
    assert '"ok": true' in capsys.readouterr().out


def test_tampered_source_is_rejected(tmp_path):
    root = tmp_path / "assets"
    shutil.copytree(ASSET_ROOT, root)
    clip = root / "kenney" / "card-place-1.ogg"
    clip.write_bytes(clip.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_assets(root)


def test_round_deal_is_scheduled_without_blocking_or_game_rng():
    backend = RecordingBackend()
    audio = AudioManager(backend)
    state = random.getstate()
    audio.handle_notice(Notice(N.ROUND_STARTED))
    assert backend.clips == [("chip-lay-1.ogg", 0.8)]
    audio.update(0.079)
    assert len(backend.clips) == 1
    audio.update(0.002)
    assert backend.clips[-1][0] == "card-place-1.ogg"
    audio.update(0.3)
    assert [name for name, _ in backend.clips[1:]] == [f"card-place-{i}.ogg" for i in range(1, 5)]
    assert random.getstate() == state


def test_mute_stops_current_and_queued_clips_and_restores_volume():
    backend = RecordingBackend()
    audio = AudioManager(backend)
    assert backend.volumes[-1] == 0.4
    audio.handle_notice(Notice(N.ROUND_STARTED))
    audio.toggle_mute()
    assert backend.volumes[-1] == 0 and audio.volume == 0.4
    assert not audio.play("win")
    audio.toggle_mute()
    audio.update(1)
    assert len(backend.clips) == 1  # delayed deals were discarded, not replayed
    assert backend.volumes[-1] == 0.4
    audio.set_volume(0.2)
    assert backend.volumes[-1] == 0.2
    audio.play("deal", delay=1)
    audio.set_volume(0)
    audio.set_volume(0.5)
    audio.update(2)
    assert len(backend.clips) == 1
    audio.close()
    assert backend.closed


@pytest.mark.parametrize("value", [-1, 1.1, float("nan"), float("inf")])
def test_invalid_volume_never_reaches_backend(value):
    backend = RecordingBackend()
    audio = AudioManager(backend)
    with pytest.raises(ValueError):
        audio.set_volume(value)
    assert audio.volume == 0.4 and backend.volumes == [0.4]


@pytest.mark.parametrize("outcome,cue", [("player", "win"), ("blackjack", "win"),
                                        ("dealer", "lose"), ("surrender", "lose"), ("push", None)])
def test_result_only_plays_on_settlement(outcome, cue):
    backend = RecordingBackend()
    audio = AudioManager(backend)
    for kind in (N.PLAYER_BLACKJACK, N.PLAYER_BUST, N.DEALER_BUSTS, N.SURRENDERED):
        audio.handle_notice(Notice(kind))
    assert not backend.clips
    audio.handle_notice(Notice(N.ROUND_SETTLED, data={"result": SimpleNamespace(outcome=outcome)}))
    assert len(backend.clips) == (1 if cue else 0)
    if cue:
        assert backend.clips[0][0] == audio.catalog[cue].files[0].name


def test_only_successful_chaos_effects_play_and_unknown_notices_are_ignored():
    backend = RecordingBackend()
    audio = AudioManager(backend)
    audio.handle_notice(Notice(N.PHASE_CHANGED, data={"to": "chaos"}))
    for kind in (N.CHAOS_ACTION_REJECTED, N.CHAOS_NARRATION, "future_notice"):
        audio.handle_notice(Notice(kind))
    assert not backend.clips
    audio.handle_notice(Notice(N.ITEM_USED))
    audio.handle_notice(Notice(N.RULE_MODIFIER_APPLIED))
    assert [clip for clip, _ in backend.clips] == ["card-shuffle.ogg"] * 2
    audio.handle_notice(Notice(N.PHASE_CHANGED, data={"to": "player_turn"}))
    audio.handle_notice(Notice(N.ITEM_USED))
    assert len(backend.clips) == 2


def test_headless_manager_is_silent_and_bad_requests_fail_explicitly():
    audio = AudioManager()
    assert not audio.available and not audio.play("deal")
    with pytest.raises(ValueError, match="Unknown sound cue"):
        audio.play("unknown")
    with pytest.raises(ValueError):
        audio.play("deal", delay=-1)
    with pytest.raises(ValueError):
        audio.update(float("nan"))
