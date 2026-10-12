"""AssetManager — resolve asset ids to Surfaces / Fonts, with caching.

`image(id)` first follows an alias, if one is set and its target exists
(file or manifest entry): the equipped cosmetics map base ids such as
`card_back` to their own art (`set_aliases`). Then, for the resolved id:
  1. a file named `<id>.png|.jpg|.jpeg|.webp` anywhere under the asset dirs
     (first dir wins; subfolders allowed),
  2. a portrait contributed by a content pack's AI persona,
  3. the manifest placeholder,
  4. a magenta checker so missing art is obvious.

Fonts come from a `fonts/` folder in an asset dir. Files named by role are
used for that role: `ui`, `ui-bold`, `display`, `display-bold` (any font
extension). Otherwise the first font file found serves every role, and
without any the system fonts in SYSTEM_FONTS are tried.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pygame

from chaos_blackjack.content.ai_profile import persona_image
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
        self.audio = None  # App binds its SoundManager; standalone widgets stay silent.
        self._files: dict[str, Path] = {}
        self._font_files: dict[str, Path] = {}  # role (or "any") -> file
        self._images: dict[tuple[str, tuple[int, int] | None], pygame.Surface] = {}
        self._aliases: dict[str, str] = {}
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
        return asset_id in self._files or persona_image(asset_id) is not None

    def source(self, asset_id: str) -> str:
        """'file' | 'placeholder' | 'missing' — reported by validation and previews."""
        if self.has_file(asset_id):
            return "file"
        return "placeholder" if asset_id in self.manifest else "missing"

    def path(self, asset_id: str) -> Path | None:
        return self._files.get(asset_id) or persona_image(asset_id)

    # --------------------------------------------------------------- aliases

    def set_aliases(self, aliases: dict[str, str]) -> None:
        """Draw `aliases[id]` wherever `id` is asked for (equipped cosmetics).
        Replaces the previous aliases; the image cache is keyed by the drawn id,
        so switching looks needs no reload."""
        self._aliases = {k: v for k, v in aliases.items() if k != v}

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def resolve(self, asset_id: str) -> str:
        """The id actually drawn for `asset_id`. An alias without a file or
        manifest placeholder is ignored, so missing skin art shows the base look."""
        target = self._aliases.get(asset_id)
        if target is not None and (self.has_file(target) or target in self.manifest):
            return target
        return asset_id

    # ---------------------------------------------------------------- images

    def image(self, asset_id: str, size: tuple[int, int] | None = None, *, alias: bool = True) -> pygame.Surface:
        """Surface for `asset_id` (after aliases unless `alias` is False, e.g. for
        wardrobe previews of a specific look), scaled exactly to `size` if given."""
        if alias:
            asset_id = self.resolve(asset_id)
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

    def image_fit(self, asset_id: str, box: tuple[int, int], *, alias: bool = True) -> pygame.Surface:
        """Scale to fit inside `box`, keeping aspect ratio."""
        w, h = self.image(asset_id, alias=alias).get_size()
        k = min(box[0] / w, box[1] / h)
        return self.image(asset_id, (max(1, round(w * k)), max(1, round(h * k))), alias=alias)

    def _load_base(self, asset_id: str) -> pygame.Surface:
        path = self.path(asset_id)
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
