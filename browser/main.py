# /// script
# dependencies = ["pygame-ce"]
# ///
"""Pygbag entry point: the repository's original Pygame scenes."""
import asyncio
import os
import sqlite3
from pathlib import Path

sqlite3.__path__.append(str(Path(__file__).resolve().parent / "stdlib/sqlite3"))

os.environ["CHAOS_USE_LLM"] = "0"
os.environ["CHAOS_DB"] = "/tmp/chaos-browser.db"


async def main():
    import platform
    window = platform.window
    try:
        # Imports can initialize balance data. Report those failures as well as
        # errors after the app has started, instead of leaving a loading screen.
        from chaos_blackjack.gui.browser import BrowserStore
        from chaos_blackjack.gui.app import App
        from chaos_blackjack.app.config import RunConfig
        from chaos_blackjack.data.balance import load_balance

        # Authentication and cloud restore complete before the VM is loaded.
        store = BrowserStore(window)
        app = App(run_config=RunConfig.from_balance(load_balance(), use_llm=False))
        await app.run_async(on_frame=store.frame)
        store.flush()
    except Exception:
        window.chaosFailed()
        raise
    finally:
        window.chaosClosed()


asyncio.run(main())
