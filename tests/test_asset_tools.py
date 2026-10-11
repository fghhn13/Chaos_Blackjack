"""Art pipeline scripts: validator (pygame) and processor (Pillow + numpy)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def validate():
    return _load("validate_assets")


def _save(path: Path, size, color, alpha=True, hole=True) -> None:
    flags = pygame.SRCALPHA if alpha else 0
    surf = pygame.Surface(size, flags, 32)
    surf.fill(color)
    if alpha and hole:
        surf.fill((0, 0, 0, 0), pygame.Rect(0, 0, 4, 4))
        for corner in ((size[0] - 1, 0), (0, size[1] - 1), (size[0] - 1, size[1] - 1)):
            surf.set_at(corner, (0, 0, 0, 0))
    pygame.image.save(surf, str(path))


def _rows(validate, tmp_path, *extra):
    code = validate.main(["--dir", str(tmp_path), "--json", *extra])
    return code


def test_validator_flags_size_alpha_and_names(validate, tmp_path, capsys) -> None:
    pygame.init()
    _save(tmp_path / "peek.png", (256, 256), (200, 160, 90, 255))  # good icon
    _save(tmp_path / "swap.png", (256, 256), (200, 160, 90), alpha=False)  # no alpha
    _save(tmp_path / "chip_1.png", (200, 200), (230, 220, 200, 255))  # wrong size
    _save(tmp_path / "table_background.png", (1920, 1080), (30, 60, 50, 255))  # has a hole
    _save(tmp_path / "card-back.png", (512, 768), (40, 80, 60, 255))  # bad name

    assert _rows(validate, tmp_path) == 1
    import json

    data = json.loads(capsys.readouterr().out)
    status = {r["id"]: r["status"] for r in data["assets"]}
    assert status["peek"] == "OK"
    assert status["swap"] == "FAIL"
    assert status["chip_1"] == "FAIL"
    assert status["table_background"] == "FAIL"
    assert status["card_back"] == "MISSING"
    assert len(data["unrecognized"]) == 1
    assert Path(data["unrecognized"][0]["file"]).name == "card-back.png"
    assert data["unrecognized"][0]["suggested_id"] == "card_back"


def test_validator_require_all(validate, tmp_path, capsys) -> None:
    pygame.init()
    _save(tmp_path / "peek.png", (256, 256), (200, 160, 90, 255))
    assert _rows(validate, tmp_path) == 0
    assert _rows(validate, tmp_path, "--require-all") == 1
    capsys.readouterr()


def test_processor_contain_cover_and_upscale_guard(tmp_path) -> None:
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    from PIL import Image, ImageDraw

    tools = _load("asset_tools")
    specs = tools.load_specs()

    src = tmp_path / "raw_peek.png"
    img = Image.new("RGBA", (1000, 800), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((100, 300, 500, 700), fill=(180, 160, 110, 254))
    img.save(src)
    out = tmp_path / "out"
    res = tools.process(tools.Job(id="peek", src=src, out_dir=out), specs)
    done = Image.open(out / "peek.png")
    assert done.size == (256, 256) and done.mode == "RGBA"
    assert done.getpixel((128, 128))[3] == 255  # 254 body snapped to opaque
    assert done.getpixel((0, 0))[3] == 0
    assert res["written"]

    with pytest.raises(SystemExit, match="exists"):
        tools.process(tools.Job(id="peek", src=src, out_dir=out), specs)

    bg = tmp_path / "bg.png"
    Image.new("RGB", (1000, 600), (20, 50, 40)).save(bg)
    with pytest.raises(SystemExit, match="allow-upscale"):
        tools.process(tools.Job(id="table_background", src=bg, out_dir=out), specs)
    tools.process(tools.Job(id="table_background", src=bg, out_dir=out, allow_upscale=True), specs)
    flat = Image.open(out / "table_background.png")
    assert flat.size == (1920, 1080) and flat.mode == "RGB"
    assert src.exists() and Image.open(src).size == (1000, 800)  # source untouched


def test_fetch_icons_splits_glued_arc_flags() -> None:
    fetch = _load("fetch_icons")
    d = "M10 10a5 5 0 0110 10l-2.5.5z"
    assert fetch.normalize_path(d) == "M 10 10 a 5 5 0 0 1 10 10 l -2.5 .5 z"
    svg = '<svg><path fill="#fff" d="M0 0h1v1z"/></svg>'
    assert 'd="M 0 0 h 1 v 1 z"' in fetch.normalize_svg(svg)


def test_font_roles_pick_files_by_name(tmp_path) -> None:
    from chaos_blackjack.gui.assets import AssetManager

    pygame.init()
    shipped = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    if not (shipped / "ui.ttf").exists():
        pytest.skip("bundled fonts not present")
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    for name in ("ui.ttf", "display.ttf"):
        (fonts / name).write_bytes((shipped / name).read_bytes())
    m = AssetManager([tmp_path])
    assert m._font_files["ui"].name == "ui.ttf"  # noqa: SLF001
    assert m._font_files["display"].name == "display.ttf"  # noqa: SLF001
    ui, display = m.font(24), m.font(24, role="display")
    assert ui.size("Chaos") != display.size("Chaos")
    assert m.font(24, bold=True).get_bold()  # no ui-bold file -> synthetic bold
    # The display face ships heavy: asking for bold must not embolden it again.
    assert m.font(24, bold=True, role="display").size("Chaos") == display.size("Chaos")


def test_button_key_hint_from_hotkey() -> None:
    from chaos_blackjack.gui.widgets import key_name

    pygame.init()
    assert key_name(pygame.K_h) == "H"
    assert key_name(pygame.K_RETURN) == "Enter"
    assert key_name(None) == ""
