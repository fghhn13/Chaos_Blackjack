"""J-54 "Joker Reshuffler": the deck-rebuilding expansion table (demo).

Design: docs/design/J54_TABLE.md. Importing this package registers the
table's mechanics for the `j54` mode; the mode itself is in
chaos_blackjack/modes and its deck rules in rules/plugins/j54_deck.py.
"""

from chaos_blackjack.app.table_mechanics import register_table
from chaos_blackjack.j54.table import J54Table

register_table("j54", J54Table)

__all__ = ["J54Table"]
