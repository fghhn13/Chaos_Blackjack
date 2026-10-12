# Original Pygame GUI in a browser

The browser game runs the repository's Pygame scenes in CPython WebAssembly
using Pygbag 0.9.3 and pygame-ce 2.5.7. The desktop entry point remains synchronous;
`App.run_async()` yields once per frame for the browser. Offline Chaos jobs run
without OS threads. Billed LLM clients are never selected by the browser entry point.

## Build and test locally

```sh
python -m pip install '.[browser,gui,dev]'
python scripts/build_browser.py
# Set BLACKJACK_REGISTRATION_TOKEN to a development-only 16-digit value.
python -m chaos_blackjack.web
```

Open http://127.0.0.1:8000, register, click Play, then click the game when prompted
to unlock browser audio. The original menu, three player slots, Classic/Chaos,
upgrades, Collection, history, settings and animations are used directly.
Keyboard and mouse work on desktop. Phones can use touch controls; landscape and
the Fullscreen button offer more room for the fixed 1280x720 layout.

`package-files.txt` explicitly selects shipped assets and package resources.
The builder adds Python source under `chaos_blackjack` except the server package.
No .env, credentials, databases, raw artwork or local scratch are packaged.
New non-Python resources must be added to that manifest. The two untracked local
card-back PNG files are intentionally excluded. The smaller WASM standard library
needs the pure Python `sqlite3.dump` helper, which is bundled from the build Python.

All runtime files and the Pygame wheel are served from `/play/runtime/` on the
same host. The uncompressed bundle is approximately 24 MB; production Nginx
compresses runtime downloads. Game assets use private caches with ETag
revalidation after authentication, so reloads avoid transferring unchanged
files. Account responses and the game HTML retain `no-store`. The loading
message shows elapsed time and tells players when to click the game to unlock
audio. A slow first download may take a few minutes; no third-party CDN is needed
by players. Builds download upstream files to an operator-configurable cache.
The game frame needs inline scripts and JavaScript/WASM evaluation for Emscripten;
the account page retains its stricter CSP. Game files require an active account.

## Saves and accounts

Authentication, invitation checks, account administration and CSRF protection
remain on the server. Gameplay and progression execute in the browser. They are
single-player client saves, not server-verified scores.

Once per second, SQLite is exported through its standard `iterdump()` API.
Changed snapshots are backed up in localStorage under the account ID and uploaded
to `/api/browser-save`. The server stores these snapshots as opaque strings and
never executes the contained SQL. Restoring happens only inside the browser's
virtual database. No packed deck is inspected by the bridge.

Cloud writes require the prior revision. Stale tabs stop instead of overwriting
newer progress. Local backups are kept when the network fails; conflicts are
archived under a `:conflict:` key. The save status shows whether synchronization
succeeded. Wait for "Saved to your account" before closing. Snapshots have a 2 MB
limit. Account disablement or session expiry blocks cloud access and resource loads.
Legacy server-side AgentSession runs remain stored separately.

## Dependencies

Upstream runtime: [pygame-web](https://github.com/pygame-web/pygbag),
[CPython](https://github.com/python/cpython), and
[pygame-ce](https://github.com/pygame-community/pygame-ce).
Their bundled license notices apply. Game fonts and audio retain the credits
and licenses distributed in `assets/` and `chaos_blackjack/audio/assets/`.
