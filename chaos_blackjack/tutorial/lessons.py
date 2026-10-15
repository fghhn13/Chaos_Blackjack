"""What the practice table deals and what Poker Head says (docs/design/TUTORIAL.md).

Four scripted hands each teach one button (only that button works on the first decision), then one free
hand where the strategy chart's advice is shown. Cards are "<rank><suit>": your two, the dealer's up and
face-down card, then the cards drawn in order (the rest of the deck follows, shuffled).

The other onboarding speeches live here too: opening the Poker Head table (after a top-stake Classic win)
and the first visit to it (builds, then rules).
"""

from __future__ import annotations

from dataclasses import dataclass

from chaos_blackjack.content.host_script import HostLine

Beat = tuple[str, str]   # (mood, text)


@dataclass(frozen=True)
class Lesson:
    action: str | None             # the button this hand teaches (None = a free hand)
    deal: tuple[str, ...]          # scripted cards; () = shuffled
    before: tuple[Beat, ...]       # while you bet
    turn: tuple[Beat, ...]         # when your cards are dealt
    after: tuple[Beat, ...]        # once the hand is settled
    then: str | None = None        # the only button after the taught one (e.g. stand after a hit)


WELCOME: tuple[Beat, ...] = (
    ("welcome", "Welcome to my table. Before you sit at a real one, a few practice hands. The rules are short."),
    ("present_card", "Get closer to 21 than me without going over. Number cards count their number, "
                     "J, Q and K count 10, an ace counts 11 or 1, whichever helps you."),
    ("neutral", "Go over 21 and you bust: you lose at once, whatever I hold. I draw until I reach 17, then I stop. "
                "If I bust, you win."),
    ("present_card", "An ace with a ten-card in your first two is a blackjack and pays 3 to 2. "
                     "A win pays your bet, a tie gives it back."),
    ("neutral", "These are practice chips, but treat them as real: bets are capped at a quarter of your cash. "
                "Chips are not endless. Bet, and I deal."),
)

LESSONS: tuple[Lesson, ...] = (
    Lesson(
        "stand", ("K♠", "7♥", "6♦", "10♣", "9♥"),
        before=(("neutral", "First hand. Pick a bet with the chips and press Deal."),),
        turn=(("present_card", "You hold 17. I show a 6, and my other card is face down."),
              ("neutral", "Any card above a 4 would bust you. And a dealer showing 2 to 6 is in trouble: "
                          "I must keep drawing, and I bust often. Press Stand and let me draw.")),
        after=(("startled", "I drew and went over. That is Stand: keep what you have and make me draw."),),
    ),
    Lesson(
        "hit", ("9♣", "5♦", "7♠", "10♦", "6♥"),
        before=(("neutral", "Next hand. Bet again."),),
        turn=(("present_card", "14 against my 7. Count my hidden card as a 10 and I am already on 17."),
              ("neutral", "Standing on 14 would lose to almost anything I make. Press Hit for another card.")),
        after=(("displeased", "Hit took you to 20, and my 17 had to stop. Hit when your total is too low "
                              "to win as it is."),),
        then="stand",
    ),
    Lesson(
        "double", ("6♠", "5♥", "6♣", "9♦", "10♠", "K♥"),
        before=(("neutral", "Third hand. Bet — this one can pay twice."),),
        turn=(("present_card", "11, and I show a 6. Any ten-card gives you 21."),
              ("neutral", "Press Double: your bet doubles, you get exactly one more card and then stand. "
                          "Only on your first two cards, and only when you can cover the bet.")),
        after=(("startled", "Twice your bet. Double when one card is very likely to put you ahead."),),
    ),
    Lesson(
        "surrender", ("10♥", "6♣", "10♠", "Q♦"),
        before=(("neutral", "Fourth hand. Not every hand can be won."),),
        turn=(("suspicious", "16 against my 10: about the worst start there is. Hit and you bust often; "
                             "stand and I usually beat 16."),
              ("neutral", "Press Surrender: you give up the hand and keep half your bet. Only as your first "
                          "decision.")),
        after=(("hidden_card", "I had 20. Surrender lost you half instead of all of it."),),
    ),
    Lesson(
        None, ("A♠", "K♦", "9♣", "7♥"),
        before=(("neutral", "Fifth hand. This one you only watch."),),
        turn=(),   # a natural settles before anyone moves
        after=(("startled", "An ace and a ten-card as your first two: a natural blackjack. It pays 3 to 2 at once, "
                            "before anyone moves."),
               ("neutral", "If I have one too, it is a tie. If only I have one, you lose your bet straight away, "
                           "whatever you were planning.")),
    ),
    Lesson(
        None, (),
        before=(("neutral", "Last practice hand. Every button works now; I will tell you what the chart says."),),
        turn=(),   # the chart's advice for the hand dealt (TutorialTable.advice)
        after=(),
    ),
)

CHART: tuple[Beat, ...] = (
    ("present_card", "This card is the best any player can do against me: for each of your hands and each card "
                     "I show, the move that loses the least."),
    ("neutral", "Play it perfectly and the house still wins a little in the long run. Blackjack is a game of luck."),
    ("welcome", "That is why my tables sell items: they let you see cards, change them or bend the payout. "
                "Used well, they turn a little luck into an edge."),
    ("neutral", "Start at the Classic Table. Win it with the top stake and I will show you my own table. "
                "The chart stays in the Collection under How to play."),
)

UNLOCK_POKER_HEAD: tuple[Beat, ...] = (
    ("startled", "Four hundred chips from a hundred. You do not play like a tourist."),
    ("neutral", "Every dealer runs a different table, with rules of their own. Beat one and the next one notices."),
    ("welcome", "Poker Head's Table is open. Bring at least 400 chips; the stakes and the winnings are bigger, "
                "and the rules are mine."),
)

UNLOCK_J54: tuple[Beat, ...] = (
    ("displeased", "You beat my own table. Someone else has been watching you play."),
    ("neutral", "J-54's Table is open. It does not bend the rules; it rewrites the deck."),
)

# Poker Head's relief (meta: a vault that cannot cover the Classic Table's minimum stake is topped up).
FIRST_RELIEF: tuple[Beat, ...] = (
    ("displeased", "Broke already? Do not look at me like that. Nobody leaves my house with empty pockets."),
    ("present_card", "Here: enough for a seat at the Classic Table. Every time you go broke I slide a little more "
                     "across, up to a limit, and your membership raises that limit."),
    ("neutral", "Win a run and we start counting again. Now sit down and play properly."),
)

RELIEF: tuple[Beat, ...] = (
    ("displeased", "Broke again. Here, enough for another seat at the Classic Table."),
    ("neutral", "Do not make a habit of it."),
)

PH_INTRO_BUILD: tuple[Beat, ...] = (
    ("welcome", "At this table you build. Two kinds of buffs."),
    ("present_card", "A core changes what you can do: a different double, a later surrender. You choose one now, "
                     "from two I offer, or take chips instead. It stays all run."),
    ("neutral", "Build buffs come from my shop between hands. They multiply what a hand pays or protect you. "
                "Three slots; when they are full you replace one, and you may discard one before you bet."),
)

PH_INTRO_RULES: tuple[Beat, ...] = (
    ("suspicious", "And now, my rules. From time to time I change the table: card values, bust limits, ties."),
    ("neutral", "A rule stays a few rounds, or until something removes it. No more than two at a time. Light ones "
                "change a card; heavy ones change the game, and those wait until round nine."),
    ("present_card", "The rules panel lists what is in force and for how long. Read it before you bet."),
)


def beats(lines: tuple[Beat, ...]) -> list[HostLine]:
    return [HostLine(mood, text) for mood, text in lines]


__all__ = ["CHART", "FIRST_RELIEF", "LESSONS", "RELIEF", "Lesson", "PH_INTRO_BUILD", "PH_INTRO_RULES", "UNLOCK_J54", "UNLOCK_POKER_HEAD", "WELCOME", "beats"]
