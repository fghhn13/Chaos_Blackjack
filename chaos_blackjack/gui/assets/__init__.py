"""Art pipeline: manifest of known assets, procedural placeholders, loader."""

from chaos_blackjack.gui.assets.manager import AssetManager
from chaos_blackjack.gui.assets.manifest import MANIFEST, AssetSpec, register

__all__ = ["AssetManager", "AssetSpec", "MANIFEST", "register"]
