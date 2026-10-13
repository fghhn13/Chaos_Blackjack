"""Importing this package registers every built-in scene.

New scene: add a module here, decorate the class with `@register_scene("name")`,
and import it below.
"""

from chaos_blackjack.gui.scenes import chaos_poke, confirm, ending, run_panel, shop, table  # noqa: F401
from chaos_blackjack.gui.scenes import history, home, meta_shop, player_select, run_result, run_setup  # noqa: F401
from chaos_blackjack.gui.scenes import codex  # noqa: F401
from chaos_blackjack.gui.scenes import profile  # noqa: F401
