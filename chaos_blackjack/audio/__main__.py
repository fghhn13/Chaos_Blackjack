"""Validate/list without a device; preview is an explicit audible operation."""

from __future__ import annotations

import argparse
import json
import time

from chaos_blackjack.audio.catalog import DEFAULT_MASTER_VOLUME, checked_volume, load_catalog, validate_assets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Casino sound catalog and asset checks")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="print cue ids, clips and gains; no audio device")
    commands.add_parser("validate", help="verify original OGG files, checksums and license; no audio device")
    preview = commands.add_parser("preview", help="play one cue through an audio device (requires pygame)")
    preview.add_argument("cue", choices=tuple(load_catalog()))
    preview.add_argument("--volume", type=checked_volume, default=DEFAULT_MASTER_VOLUME)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_assets()
        elif args.command == "list":
            result = {key: {"files": [path.name for path in cue.files], "gain": cue.gain,
                            "description": cue.description} for key, cue in load_catalog().items()}
        else:
            from chaos_blackjack.audio.manager import AudioManager
            from chaos_blackjack.audio.pygame_backend import PygameAudioBackend

            backend = PygameAudioBackend()
            audio = AudioManager(backend, volume=args.volume)
            try:
                if not audio.available:
                    raise RuntimeError(f"Audio unavailable: {backend.last_error}")
                played = audio.play(args.cue)
                if played:
                    # One clip; give the mixer time to finish, without initializing a window.
                    while backend.busy:
                        time.sleep(0.01)
                elif audio.effective_volume > 0:
                    raise RuntimeError(f"Cue could not be played: {backend.last_error}")
                result = {"ok": True, "cue": args.cue, "volume": audio.volume, "played": played}
            finally:
                audio.close()
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
