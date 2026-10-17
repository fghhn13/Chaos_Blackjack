"""J-54's exact evaluator: the meter's numbers and the heat map (J54_V2_SPEC.md section 5)."""

from __future__ import annotations

import random
import time

import pytest

from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.j54 import evaluator as ev_mod
from chaos_blackjack.j54.deck_ops import JOKER, RANKS, SUITS
from chaos_blackjack.j54.evaluator import Evaluator, HandStats, Valuation, group_of, parse_filter

TENS = ("10", "J", "Q", "K")
STAND_15 = Valuation(dealer_stand_on=15)
FACES_5 = Valuation(dealer_rules=({"op": "set", "filter": "face", "value": 5},))


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


def _deck() -> list[Card]:
    return [_c(r, s) for r in RANKS for s in SUITS]


def _joker() -> Card:
    return Card(Rank(JOKER), "")


@pytest.fixture(autouse=True)
def _fresh_cache():
    ev_mod.clear_cache()
    yield
    ev_mod.clear_cache()


# -- plain blackjack against real hands --------------------------------------


def _value(card: Card) -> int:
    r = str(card.rank)
    return 1 if r == "A" else 10 if r in TENS else int(r)


def _total(cards: list[Card]) -> int:
    hard = sum(_value(c) for c in cards)
    soft = any(str(c.rank) == "A" for c in cards)
    return hard + 10 if soft and hard + 10 <= 21 else hard


def _natural(cards: list[Card]) -> bool:
    ranks = {str(c.rank) for c in cards}
    return len(cards) == 2 and "A" in ranks and bool(ranks & set(TENS))


def _monte_carlo(evaluator: Evaluator, hands: int, seed: int) -> float:
    """Hands dealt without replacement from a fresh shuffled 52-card deck; the
    player follows the evaluator's policy for the full deck; J-54 peeks for a
    natural and draws to 17."""
    deck = _deck()
    rng = random.Random(seed)
    memo: dict[tuple, bool] = {}

    def hit(up: Card, hand: list[Card]) -> bool:
        key = (str(up.rank), tuple(sorted(str(c.rank) for c in hand)))
        if key not in memo:
            memo[key] = evaluator.should_hit(deck, up, hand)
        return memo[key]

    wins = 0
    for _ in range(hands):
        shoe = deck[:]
        rng.shuffle(shoe)
        player = [shoe.pop(), shoe.pop()]
        up, hole = shoe.pop(), shoe.pop()
        dealer = [up, hole]
        if _natural(dealer):
            continue
        if _natural(player):
            wins += 1
            continue
        while _total(player) <= 21 and hit(up, player):
            player.append(shoe.pop())
        mine = _total(player)
        if mine > 21:
            continue
        while _total(dealer) < 17:
            dealer.append(shoe.pop())
        theirs = _total(dealer)
        if theirs > 21 or mine > theirs:
            wins += 1
    return wins / hands


def test_plain_blackjack_matches_a_monte_carlo_within_one_point():
    evaluator = Evaluator(Valuation())
    stats = evaluator.stats(_deck())
    assert stats.win * 100 == pytest.approx(43.5, abs=1.0)
    assert stats.win + stats.push + stats.loss == pytest.approx(1.0, abs=1e-9)
    assert stats.capture == 0.0
    assert stats.bar == stats.win
    mc = _monte_carlo(evaluator, 20_000, seed=54)
    assert abs(stats.win - mc) < 0.01


def test_plain_blackjack_basics():
    stats = Evaluator(Valuation()).stats(_deck())
    # A natural: 2 * P(A) * P(ten) * (1 - P(J-54 natural)).
    p_nat = 2 * (4 / 52) * (16 / 52)
    assert stats.natural == pytest.approx(p_nat * (1 - p_nat))
    assert -0.06 < stats.ev < 0.0


def test_heat_has_plain_blackjacks_signs():
    heat = Evaluator(Valuation()).heat(_deck())
    assert list(heat) == [r + x for r in RANKS for x in "rb"]
    for rank in ("4", "5"):
        assert heat[rank + "r"] > 0 and heat[rank + "b"] > 0
    for rank in (*TENS, "A"):
        assert heat[rank + "r"] < 0 and heat[rank + "b"] < 0
    # Removing a five helps the most; the four ten-ranks are exactly equal.
    assert max(heat, key=heat.get) in ("5r", "5b")
    assert len({heat[t + x] for t in TENS for x in "rb"}) == 1


def test_heat_lists_only_groups_present_and_reads_per_card():
    # No sevens, no black nines, one Joker.
    deck = [c for c in _deck() if str(c.rank) != "7"
            and not (str(c.rank) == "9" and c.suit in ("♠", "♣"))] + [_joker()]
    heat = Evaluator(Valuation()).heat(deck)
    assert "7r" not in heat and "7b" not in heat
    assert "9r" in heat and "9b" not in heat
    assert all(g != JOKER for g in heat)
    assert len(heat) == 23


# -- the rules ---------------------------------------------------------------


def test_a_j54_rule_changes_only_j54s_values():
    plain = Evaluator(Valuation())
    black = Evaluator(Valuation(dealer_rules=({"op": "bonus", "filter": "color:black", "amount": 1},)))
    for card in _deck():
        assert black.value(card, "player") == plain.value(card, "player")
        expected = plain.value(card, "dealer")[0] + (1 if card.suit in ("♠", "♣") else 0)
        assert black.value(card, "dealer")[0] == expected
    assert black.stats(_deck()).win != plain.stats(_deck()).win


def test_a_player_rule_changes_only_the_players_values():
    plain = Evaluator(Valuation())
    fives = Evaluator(Valuation(player_rules=({"op": "set", "filter": "ranks:5-6", "value": 10},)))
    for card in _deck():
        assert fives.value(card, "dealer") == plain.value(card, "dealer")
        if str(card.rank) in ("5", "6"):
            assert fives.value(card, "player") == (10, False)
        else:
            assert fives.value(card, "player") == plain.value(card, "player")
    assert fives.stats(_deck()).win != plain.stats(_deck()).win


def test_scale_set_and_aces():
    hearts = Evaluator(Valuation(dealer_rules=({"op": "scale", "filter": "suit:♥", "factor": 2},)))
    assert hearts.value(_c("7", "♥"), "dealer") == (14, False)
    assert hearts.value(_c("7", "♦"), "dealer") == (7, False)
    aces = Evaluator(Valuation(dealer_rules=({"op": "set", "filter": "rank:A", "value": 1},)))
    assert aces.value(_c("A"), "dealer") == (1, False)        # set drops the soft value
    assert aces.value(_c("A"), "player") == (1, True)
    soft = Evaluator(Valuation(dealer_rules=({"op": "set", "filter": "rank:A", "value": 1, "soft": True},)))
    assert soft.value(_c("A"), "dealer") == (1, True)


def test_stand_on_15_raises_the_bar_and_faces_5_lowers_it():
    plain = Evaluator(Valuation()).stats(_deck()).win
    stand = Evaluator(STAND_15).stats(_deck()).win
    faces = Evaluator(FACES_5).stats(_deck()).win
    assert stand > plain > faces
    # The lab's numbers.
    assert stand * 100 == pytest.approx(46.5, abs=0.1)
    assert faces * 100 == pytest.approx(37.8, abs=0.1)


def test_bust_lines_are_per_side():
    plain = Evaluator(Valuation()).stats(_deck())
    margin = Evaluator(Valuation(player_bust=22)).stats(_deck())
    assert margin.win > plain.win and margin.ev > plain.ev
    tight = Evaluator(Valuation(dealer_bust=20)).stats(_deck())
    assert tight.win > plain.win


def test_filters():
    def m(text: str, rank: str, suit: str = "♠") -> bool:
        return parse_filter(text)(rank, suit)

    assert m("parity:even", "Q") and m("parity:even", "10") and not m("parity:even", "K")
    assert m("color:black", "5", "♣") and not m("color:black", "5", "♥")
    assert m("suit:H", "5", "♥") and m("suit:♥", "5", "♥")
    assert m("face", "J") and not m("face", "10")
    assert m("low", "6") and not m("low", "7")
    assert m("rank:7", "7") and m("ranks:4-6", "5") and not m("ranks:4-6", "7")
    assert m("face & color:red", "K", "♦") and not m("face & color:red", "K", "♠")
    assert m("rank:2 | rank:3", "3") and m("!face", "9")
    assert not m("any", JOKER, "") and m("all", JOKER, "") and m("joker", JOKER, "")
    assert not m("parity:odd", JOKER, "") and not m("color:red", JOKER, "")
    with pytest.raises(ValueError):
        parse_filter("colour:blue")
    with pytest.raises(ValueError):
        Evaluator(Valuation(dealer_rules=({"op": "double", "filter": "any"},)))
    with pytest.raises(ValueError):
        Evaluator(Valuation(dealer_rules=({"op": "bonus", "filter": "any"},)))


# -- the Joker -----------------------------------------------------------------


def test_the_joker_raises_capture_and_is_a_soft_ace_for_the_player_only():
    evaluator = Evaluator(Valuation())
    assert evaluator.value(_joker(), "player") == (1, True)
    assert evaluator.value(_joker(), "dealer") == (0, False)
    plain = evaluator.stats(_deck())
    with_joker = evaluator.stats(_deck() + [_joker()])
    assert plain.capture == 0.0
    # At least the chance of holding it in the first two cards.
    assert with_joker.capture > 1 - (52 / 53) ** 2
    assert with_joker.capture < 0.1
    assert with_joker.win > plain.win
    # joker_in_deck adds the Joker to a deck without one, never a second one.
    flagged = Evaluator(Valuation(joker_in_deck=True))
    assert flagged.stats(_deck()).capture == pytest.approx(with_joker.capture)
    assert flagged.stats(_deck() + [_joker()]).capture == pytest.approx(with_joker.capture)


def test_the_joker_is_a_soft_ace_but_never_a_natural():
    # Twelve ten-cards and the Joker: J-54 always holds 20 (it never keeps the
    # Joker); ten + Joker is a soft 21 that wins at even money.
    deck = [_c(r, s) for r in TENS for s in ("♠", "♥", "♦")] + [_joker()]
    p, q = 1 / 13, 12 / 13
    stats = Evaluator(Valuation()).stats(deck)
    assert stats.natural == 0.0
    # Ten + ten: stand on 20 pushes, hitting wins only with the Joker; ten +
    # Joker wins; Joker + Joker (p^2) is somewhere in between.
    low = q * q * p + 2 * p * q
    assert low - 1e-9 <= stats.win <= low + p * p + 1e-9
    # The EV policy stands on 20 (a push), wins every ten + Joker and can lose
    # only Joker + Joker.
    assert 2 * p * q - p * p - 1e-9 <= stats.ev <= 2 * p * q + p * p + 1e-9
    assert stats.capture == pytest.approx(1 - q * q + q * q * p, abs=1e-9)


def test_a_deck_of_only_the_joker_is_refused():
    with pytest.raises(ValueError):
        Evaluator(Valuation()).stats([_joker()])


# -- the interface ---------------------------------------------------------------


def test_stats_and_heat_on_52_cards_take_under_a_second():
    evaluator = Evaluator(Valuation(dealer_rules=({"op": "scale", "filter": "suit:♥", "factor": 2},)))
    start = time.perf_counter()
    evaluator.stats(_deck())
    heat = evaluator.heat(_deck())
    assert time.perf_counter() - start < 1.0
    assert len(heat) == 26


def test_results_are_cached_by_composition_and_valuation():
    evaluator = Evaluator(FACES_5)
    deck = _deck()
    stats = evaluator.stats(deck)
    assert isinstance(stats, HandStats)
    assert evaluator.stats(list(reversed(deck))) is stats
    # A new evaluator with an equal valuation shares the cache.
    same = Evaluator(Valuation(dealer_rules=[{"filter": "face", "value": 5, "op": "set"}]))
    assert same.stats(deck) is stats
    assert evaluator.heat(deck) is evaluator.heat(deck[::-1])
    assert Evaluator(Valuation()).stats(deck) is not stats
    assert hash(FACES_5) == hash(same.valuation) and FACES_5 == same.valuation


def test_group_of():
    assert group_of(_c("5", "♥")) == "5r"
    assert group_of(_c("K", "♣")) == "Kb"
    assert group_of(_joker()) is None


def test_should_hit_follows_basic_play():
    evaluator = Evaluator(Valuation())
    deck = _deck()
    assert evaluator.should_hit(deck, _c("10"), [_c("10"), _c("2")])
    assert not evaluator.should_hit(deck, _c("6"), [_c("10"), _c("3")])
    assert not evaluator.should_hit(deck, _c("7"), [_c("10"), _c("9")])
    assert not evaluator.should_hit(deck, _c("7"), [_c("10"), _c("9"), _c("5")])   # bust
