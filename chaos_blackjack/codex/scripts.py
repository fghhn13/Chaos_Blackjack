"""Illustrative deals; captions avoid claims about profile-specific numbers."""

from chaos_blackjack.codex.models import DemoScript, DemoStep as Step


def _rule(rule_id, player, dealer=("10♣", "7♦"), deck=("2♣", "3♠", "K♦"), *, hit=False):
    return DemoScript(player, dealer, deck, True, (
        Step("deal", caption="The same cards before Chaos changes the table."),
        Step("apply_rule", rule_id, "The rule is active. Watch the totals and the result."),
        *((Step("hit", caption="Take the next card under the active rule."),) if hit else ()),
        Step("stand", caption="Reveal the dealer's hand."),
        Step("dealer", caption="The controller plays the dealer and settles the hand."),
    ))


def _deck_rule(rule_id):
    """J-54's rules change the deck, not this hand's totals."""
    return DemoScript(("10♠", "8♥"), ("10♣", "7♦"), ("2♣", "3♠", "K♦"), True, (
        Step("deal", caption="A fixed deal at J-54's table."),
        Step("apply_rule", rule_id, "J-54 rewrites the deck. At its table the change lasts the whole run."),
        Step("stand", caption="This hand plays as usual; later rounds deal from the changed deck."),
        Step("dealer", caption="The controller plays the dealer and settles the hand."),
    ))


RULE_DEMOS = {
    "modify_card_value": _rule("modify_card_value", ("K♠", "8♥")),
    "great_crash": _rule("great_crash", ("K♠", "Q♥")),
    "odd_even_chaos": _rule("odd_even_chaos", ("8♠", "7♥"), hit=True),
    "suit_power": _rule("suit_power", ("9♥", "7♦")),
    "fragile_bust": _rule("fragile_bust", ("10♠", "7♥"), deck=("3♣",), hit=True),
    "reverse_bust": _rule("reverse_bust", ("10♠", "9♥"), deck=("5♣",), hit=True),
    "tiebreaker_shift": _rule("tiebreaker_shift", ("10♠", "8♥"), dealer=("K♣", "8♦")),
    **{rid: _deck_rule(rid) for rid in ("j54_burn", "j54_sample_injection", "j54_redundancy_purge",
                                        "j54_ace_injection")},
}


def _item(item_id):
    shield = item_id == "shield"
    return DemoScript(("8♠", "6♥"), ("10♣", "7♦"), ("5♣", "K♦", "2♠", "9♦", "3♥"), shield, (
        Step("deal", caption="A fixed deal with the demonstration item in hand."),
        *((Step("apply_rule", "modify_card_value", "Chaos shifts the card values."),) if shield else ()),
        Step("use_item", item_id, "Use the item; its notice reports the actual effect."),
        Step("pause"),
        *((Step("hit", caption="Draw the card the item helped you assess."),) if item_id == "peek" else ()),
        Step("stand", caption="Reveal the dealer's hand."),
        Step("dealer", caption="Settle using the current rules."),
    ))


ITEM_DEMOS = {iid: _item(iid) for iid in (
    "peek", "swap", "shield", "danger_radar", "fate_oracle", "hole_card_hacker",
)}
