"""AssetManager — resolve asset ids to Surfaces / Fonts, with caching.

Lookup order for `image(id)`:
  1. a file named `<id>.png|.jpg|.jpeg|.webp` anywhere under the asset dirs
     (first dir wins; subfolders allowed),
  2. the manifest placeholder,
  3. a magenta checker so missing art is obvious.

Fonts come from a `fonts/` folder in an asset dir. Files named by role are
used for that role: `ui`, `ui-bold`, `display`, `display-bold` (any font
extension). Otherwise the first font file found serves every role, and
without any the system fonts in SYSTEM_FONTS are tried.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pygame

from chaos_blackjack.gui.assets import placeholders
from chaos_blackjack.gui.assets.manifest import MANIFEST, AssetSpec

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
FONT_EXTS = (".ttf", ".otf", ".ttc")
FONT_ROLES = ("ui", "ui-bold", "display", "display-bold")
# Tried in order when no font file ships in an asset dir's `fonts/` folder.
SYSTEM_FONTS = ("microsoftyahei", "pingfangsc", "notosanssc", "simhei", "notosanscjksc", "wenquanyimicrohei")

_FALLBACK_SIZE = (128, 128)


class AssetManager:
    def __init__(self, asset_dirs: Iterable[Path], manifest: dict[str, AssetSpec] | None = None) -> None:
        self.asset_dirs = tuple(Path(d) for d in asset_dirs)
        self.manifest = MANIFEST if manifest is None else manifest
        self._files: dict[str, Path] = {}
        self._font_files: dict[str, Path] = {}  # role (or "any") -> file
        self._images: dict[tuple[str, tuple[int, int] | None], pygame.Surface] = {}
        self._fonts: dict[tuple[int, bool, str], pygame.font.Font] = {}
        self.refresh()

    # ----------------------------------------------------------------- index

    def refresh(self) -> None:
        """Rescan asset dirs (e.g. after new art was exported) and drop caches."""
        files: dict[str, Path] = {}
        font_files: dict[str, Path] = {}
        for d in self.asset_dirs:
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*")):
                if any(part.startswith(".") for part in p.relative_to(d).parts):
                    continue
                suffix = p.suffix.lower()
                if suffix in IMAGE_EXTS:
                    files.setdefault(p.stem, p)
                elif suffix in FONT_EXTS and p.parent.name == "fonts":
                    role = p.stem.lower()
                    font_files.setdefault(role if role in FONT_ROLES else "any", p)
        self._files = files
        self._font_files = font_files
        self._images.clear()
        self._fonts.clear()

    def has_file(self, asset_id: str) -> bool:
        return asset_id in self._files

    def source(self, asset_id: str) -> str:
        """'file' | 'placeholder' | 'missing' — shown in the asset gallery."""
        if asset_id in self._files:
            return "file"
        return "placeholder" if asset_id in self.manifest else "missing"

    def path(self, asset_id: str) -> Path | None:
        return self._files.get(asset_id)

    # ---------------------------------------------------------------- images

    def image(self, asset_id: str, size: tuple[int, int] | None = None) -> pygame.Surface:
        """Surface for `asset_id`, scaled exactly to `size` if given."""
        key = (asset_id, size)
        cached = self._images.get(key)
        if cached is not None:
            return cached
        base = self._images.get((asset_id, None))
        if base is None:
            base = self._load_base(asset_id)
            self._images[(asset_id, None)] = base
        surf = base if size is None or base.get_size() == size else pygame.transform.smoothscale(base, size)
        self._images[key] = surf
        return surf

    def image_fit(self, asset_id: str, box: tuple[int, int]) -> pygame.Surface:
        """Scale to fit inside `box`, keeping aspect ratio."""
        w, h = self.image(asset_id).get_size()
        k = min(box[0] / w, box[1] / h)
        return self.image(asset_id, (max(1, round(w * k)), max(1, round(h * k))))

    def _load_base(self, asset_id: str) -> pygame.Surface:
        path = self._files.get(asset_id)
        if path is not None:
            try:
                return self._optimize(pygame.image.load(str(path)))
            except (pygame.error, OSError):
                pass  # unreadable file -> fall through to placeholder
        spec = self.manifest.get(asset_id)
        if spec is not None:
            return self._optimize(spec.placeholder(spec.size, self.font))
        return self._optimize(placeholders.missing(_FALLBACK_SIZE, self.font))

    @staticmethod
    def _optimize(surf: pygame.Surface) -> pygame.Surface:
        if pygame.display.get_surface() is None:
            return surf
        return surf.convert_alpha()

    # ----------------------------------------------------------------- fonts

    def font(self, size: int, bold: bool = False, role: str = "ui") -> pygame.font.Font:
        """`role` is "ui" (body text) or "display" (titles, headlines)."""
        key = (size, bold, role)
        f = self._fonts.get(key)
        if f is None:
            f = self._make_font(size, bold, role)
            self._fonts[key] = f
        return f

    def _make_font(self, size: int, bold: bool, role: str) -> pygame.font.Font:
        if not pygame.font.get_init():
            pygame.font.init()
        roles = [role, "ui"] if role != "ui" else ["ui"]
        for r in roles:
            if bold and f"{r}-bold" in self._font_files:
                return pygame.font.Font(str(self._font_files[f"{r}-bold"]), size)
            if r in self._font_files:
                f = pygame.font.Font(str(self._font_files[r]), size)
                f.set_bold(bold and r != "display")  # display faces ship already heavy
                return f
        if "any" in self._font_files:
            f = pygame.font.Font(str(self._font_files["any"]), size)
            f.set_bold(bold)
            return f
        for name in SYSTEM_FONTS:
            path = pygame.font.match_font(name, bold=bold)
            if path:
                return pygame.font.Font(path, size)
        return pygame.font.Font(None, size)
