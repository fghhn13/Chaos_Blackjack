"""Semantic sound ids. Clip selection is presentation-only and never uses game RNG."""

from dataclasses import dataclass


DEFAULT_MASTER_VOLUME = 0.4


@dataclass(frozen=True)
class SoundSpec:
    id: str
    description: str
    gain: float = 0.8
    variants: tuple[str, ...] = ()


def _variants(name: str) -> tuple[str, ...]:
    return tuple(f"{name}_{index}" for index in range(1, 4))


MANIFEST = {
    spec.id: spec for spec in (
        SoundSpec("card_deal", "A card starts flying from the shoe", 0.7, _variants("card_deal")),
        SoundSpec("card_flip", "A card flip reaches its midpoint", 0.7),
        SoundSpec("chip_place", "Click a betting chip", 0.8, _variants("chip_place")),
        SoundSpec("chip_stack", "The wager stack lands in the betting circle"),
        SoundSpec("chips_win", "Settlement chips start moving toward the player", 0.9),
        SoundSpec("chips_lose", "Settlement chips start moving toward the dealer", 0.7),
        SoundSpec("round_win", "A winning round banner appears", 0.65),
        SoundSpec("round_lose", "A losing round banner appears", 0.65),
        SoundSpec("blackjack", "A natural blackjack banner appears", 0.65),
        SoundSpec("bust", "A player bust is displayed with the result banner", 0.65),
        SoundSpec("push", "A push banner appears", 0.65),
        SoundSpec("chaos_glitch", "The rule glitch starts", 0.6, _variants("chaos_glitch")),
        SoundSpec("item_use", "An item use succeeds", 0.65),
        SoundSpec("button_click", "An enabled button is clicked", 0.5, _variants("button_click")),
        SoundSpec("ending_victory", "The victory screen opens", 0.7),
        SoundSpec("ending_bankrupt", "The defeat screen opens", 0.7),
    )
}
