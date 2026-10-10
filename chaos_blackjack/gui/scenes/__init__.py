"""Importing this package registers every built-in scene.

New scene: add a module here, decorate the class with `@register_scene("name")`,
and import it below.
"""

from chaos_blackjack.gui.scenes import chaos_poke, confirm, ending, gallery, items, menu, shop, table  # noqa: F401
