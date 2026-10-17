"""J-54's table: an experiment on a deck that lasts the run (docs/design/J54_V2_SPEC.md).

`table` holds the mechanics (registered for the `j54` mode when imported);
`program` is the schedule of conditions; `firmware` the player's build pick;
`deck_ops` the deck-operation engine behind removals and entropy. The mode is
in chaos_blackjack/modes and its conditions in rules/plugins/j54_conditions.py
(v1's deck rules stay in rules/plugins/j54_deck.py for the Collection).
"""
