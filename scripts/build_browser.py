"""Build a secret-free Pygbag bundle from explicitly selected repository files."""
from pathlib import Path
import shutil
import subprocess
import sys
import json
import urllib.request
import sqlite3.dump
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "build" / "pygame"
CDN = "https://pygame-web.github.io/cdn/"
RUNTIME = ("0.9.3/pythons.js", "0.9.3/cpythonrc.py", "0.9.3/cpython312/main.js",
           "0.9.3/cpython312/main.data", "0.9.3/cpython312/main.wasm",
           "0.9.3/empty.ogg", "index-0.9.3-cp312.json",
           "cp312/pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl")


def runtime_file(name):
    cache = Path(__import__("os").environ.get("BLACKJACK_RUNTIME_CACHE", ROOT / "build/runtime-cache")) / name
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.is_file():
        temp = cache.with_suffix(cache.suffix + ".part")
        with urllib.request.urlopen(CDN + name, timeout=120) as response, temp.open("wb") as target:
            shutil.copyfileobj(response, target)
        temp.replace(cache)
    return name, cache


def main():
    STAGE.mkdir(parents=True, exist_ok=True)
    # An allowlist excludes .env, databases, raw art and user scratch files.
    for folder in ("chaos_blackjack", "assets"):
        target = STAGE / folder
        if target.exists():
            shutil.rmtree(target)
    files = (ROOT / "browser/package-files.txt").read_text(encoding="utf-8").splitlines()
    files += [p.relative_to(ROOT).as_posix() for p in (ROOT / "chaos_blackjack").rglob("*.py")
              if "__pycache__" not in p.parts]
    for name in sorted(set(files)):
        if not name or name.startswith("chaos_blackjack/web/"):
            continue
        source = ROOT / name
        if source.is_file():
            dest = STAGE / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
    shutil.copyfile(ROOT / "browser/main.py", STAGE / "main.py")
    # The compact WASM stdlib omits sqlite3.dump; ship the matching pure Python helper.
    helper = STAGE / "stdlib/sqlite3/dump.py"
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sqlite3.dump.__file__, helper)
    subprocess.run([sys.executable, "-m", "pygbag", "--build", "--no_opt", str(STAGE)],
                   cwd=ROOT, check=True)
    web = STAGE / "build/web"
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, cache in pool.map(runtime_file, RUNTIME):
            target = web / "runtime" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cache, target)
    # Only Pygame is available to the game. All VM and wheel requests stay local.
    index = json.loads((web / "runtime/index-0.9.3-cp312.json").read_text())
    index = {"-CDN-": "/play/runtime/", "pygame": index["pygame"]}
    (web / "runtime/index-0.9.3-cp312.json").write_text(json.dumps(index), encoding="utf-8")
    loader = web / "runtime/0.9.3/pythons.js"
    loader.write_text(loader.read_text().replace("credentials: 'omit'", "credentials: 'same-origin'")
                     .replace("fetch(url, flags || FETCH_FLAGS)", "fetch(url, {...(flags || FETCH_FLAGS), credentials: 'same-origin'})")
                     .replace("vm.PyConfig.orig_argv = vm.cpy_argv",
                     "vm.PyConfig.orig_argv = [...vm.cpy_argv, 'PYGPI=' + location.origin + '/play/runtime/']"), encoding="utf-8")
    page = (web / "index.html").read_text(encoding="utf-8")
    page = page.replace(CDN + "0.9.3/", "/play/runtime/0.9.3/")
    page = page.replace('data-os="vtx,snd,gui"', 'data-os="stdout,snd,gui"')
    page = page.replace('can_close : 0', 'can_close : 1')
    page = page.replace('<script src="/play/runtime/0.9.3//browserfs.min.js"></script>', '')
    page = page.replace('cdn : "/play/runtime/0.9.3/"', 'cdn : location.origin + "/play/runtime/0.9.3/"')
    page = page.replace('platform.document.body.style.background = "#7f7f7f"', 'platform.document.body.style.background = "#111016"')
    page = page.replace('src="/play/runtime/0.9.3/empty.html"', 'src="about:blank"')
    bridge = '''<script>
window.chaosInitialSave = window.parent.chaosInitialSave || '';
window.chaosSave = snapshot => window.parent.chaosSave(snapshot);
window.chaosClosed = () => window.parent.chaosClosed();
window.chaosFailed = () => window.parent.chaosFailed();
</script><style>
html,body{background:#111016!important;overflow:hidden}#pyconsole,#crt,#system{display:none!important}
#stdout{display:none!important}#infobox{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:#111016;color:#e5d8b8;font:18px system-ui;z-index:10}
</style>'''
    page = page.replace('</head>', bridge + '</head>')
    (web / "index.html").write_text(page, encoding="utf-8")
    print(f"Browser bundle: {STAGE / 'build/web'}")


if __name__ == "__main__":
    main()
