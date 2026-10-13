"""J-54 "Joker Reshuffler": the deck-rebuilding expansion table (demo).

Design: docs/design/J54_TABLE.md. `deck_ops` is the deck-operation engine
shared by the table's rules, contracts and entropy; `table` holds the
mechanics (registered for the `j54` mode when imported); `contracts` is the
shop catalog. The mode itself is in chaos_blackjack/modes and its rules in
rules/plugins/j54_deck.py.
"""
