"""Desktop workers and immediate, offline jobs for the single-threaded web VM."""
import sys
from threading import Thread


def start_worker(target, args, *, name):
    if sys.platform == "emscripten":
        # Web entry points explicitly select StubLLM. No network job runs here.
        target(*args)
    else:
        Thread(target=target, args=args, name=name, daemon=True).start()
