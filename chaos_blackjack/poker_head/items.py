"""Active consumables: one small handler per product.

The table checks the catalog phases (`ProductDef.phases`) and the pending
choice first; a handler adds only its own conditions (`usability`), lists
targets when it needs one (`targets`) and applies itself (`apply`). A use
that is not allowed spends nothing. Handlers act only through the
`BuildContext` (docs/design/ITEM_ARCHITECTURE.md §5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chaos_blackjack.app.choice import USABLE, ChoiceOption, Usability, unusable
from chaos_blackjack.app.view import Action
from chaos_blackjack.poker_head.catalog import PRODUCTS, product

if TYPE_CHECKING:
    from chaos_blackjack.poker_head.context import BuildContext
    from chaos_blackjack.poker_head.ownership import Holding


class ItemHandler:
    """Default: usable in its catalog phases, no target, no effect."""

    def __init__(self, ctx: "BuildContext", product_id: str) -> None:
        self.ctx = ctx
        self.id = product_id

    def usability(self, holding: "Holding") -> Usability:
        return USABLE

    def targets(self, holding: "Holding") -> tuple[ChoiceOption, ...]:
        """Options for a targeted item (empty: it needs no target)."""
        return ()

    def prompt(self) -> str:
        return "Choose a target."

    def apply(self, holding: "Holding", target: str) -> str:
        """Change the round; return the result message."""
        raise NotImplementedError

    def after(self) -> None:
        """Runs once the item is spent (e.g. Loss Waiver then surrenders)."""


HANDLERS: dict[str, type[ItemHandler]] = {}


def handler(*ids: str):
    def register(cls: type[ItemHandler]) -> type[ItemHandler]:
        for item_id in ids:
            HANDLERS[item_id] = cls
        return cls
    return register


def build_handler(ctx: "BuildContext", product_id: str) -> ItemHandler:
    return HANDLERS[product_id](ctx, product_id)


def _needs_deck(ctx: "BuildContext") -> Usability:
    return USABLE if ctx.deck else unusable("The deck is empty.")


# --- cores ------------------------------------------------------------------------


@handler("ph_gift")
class Invitation(ItemHandler):
    def usability(self, holding):
        return unusable("Answered at the start of the run.")


@handler("ph_change")
class AmendmentLetter(ItemHandler):
    def usability(self, holding):
        if self.ctx.table.loadout.no_core:
            return unusable("You took the opening chips: no core this run.")
        return USABLE if self.targets(holding) else unusable("No other core is on offer.")

    def targets(self, holding):
        current = self.ctx.table.loadout.core
        return tuple(self.ctx.table.core_option(c) for c in holding.choices if c != current)

    def prompt(self):
        return "Choose your new core. Your permanents, items and contracts stay."

    def apply(self, holding, target):
        self.ctx.table.choose_core(target)
        return f"Core changed to {PRODUCTS[target].name}."


# --- information ---------------------------------------------------------------------


@handler("ph_peek")
class CardLens(ItemHandler):
    def usability(self, holding):
        return _needs_deck(self.ctx)

    def apply(self, holding, target):
        rank = str(self.ctx.deck[0].rank)
        self.ctx.round.shown = [rank]
        return f"Next card: {rank} (Card Lens)."


@handler("ph_hole")
class HoleProbe(ItemHandler):
    def usability(self, holding):
        return unusable("The hole card is already visible.") if self.ctx.hole_revealed else USABLE

    def apply(self, holding, target):
        self.ctx.reveal_hole()
        hole = self.ctx.state.dealer_hand[1]
        return f"Dealer's hole card: {hole.rank}{hole.suit} (Hole Probe)."


@handler("ph_radar")
class RiskPointer(ItemHandler):
    def usability(self, holding):
        return _needs_deck(self.ctx)

    def apply(self, holding, target):
        total = self.ctx.value(self.ctx.player_hand + self.ctx.deck[:1])
        return ("BUST if you hit" if self.ctx.is_bust(total) else "Safe to hit") + " (Risk Pointer)."


@handler("ph_oracle")
class FateForecast(ItemHandler):
    def usability(self, holding):
        return unusable("Already forecast this round.") if self.ctx.round.forecast else USABLE

    def apply(self, holding, target):
        cards = self.ctx.table.forecast_cards()
        self.ctx.round.forecast = [f"{c.rank}{c.suit}" for c in cards]
        self.ctx.round.forecast_changed = False
        return "Your opening cards: " + " ".join(self.ctx.round.forecast) + " (Fate Forecast)."


# --- changing cards -----------------------------------------------------------------------


@handler("ph_swap")
class SleeveClip(ItemHandler):
    def usability(self, holding):
        return _needs_deck(self.ctx)

    def apply(self, holding, target):
        state = self.ctx.state
        self.ctx.set_state(state.with_player_hand((state.deck[0],) + state.player_hand[1:]).with_deck(state.deck[1:]))
        self.ctx.table.deck_changed()
        return "Sleeve Clip: your first card was replaced."


@handler("ph_aces")
class AcesToTheTop(ItemHandler):
    def usability(self, holding):
        ranks = [str(c.rank).upper() for c in self.ctx.deck]
        if "A" not in ranks:
            return unusable("No ace is left in the deck.")
        if ranks[0] == "A":
            return unusable("The next card is already an ace.")
        return USABLE

    def apply(self, holding, target):
        deck = self.ctx.state.deck
        i = next(i for i, c in enumerate(deck) if str(c.rank).upper() == "A")
        self.ctx.set_state(self.ctx.state.with_deck((deck[i],) + deck[:i] + deck[i + 1:]))
        self.ctx.table.deck_changed()
        return "Next card: an ace (Aces to the Top)."


@handler("ph_undo")
class CardRecall(ItemHandler):
    def usability(self, holding):
        return USABLE if len(self.ctx.player_hand) > 2 else unusable("Keep at least two cards.")

    def apply(self, holding, target):
        self.ctx.set_state(self.ctx.state.with_player_hand(self.ctx.player_hand[:-1]))
        return "Card Recall: your last card was removed."


# --- rules ---------------------------------------------------------------------------------


@handler("ph_remove")
class ClauseRemoval(ItemHandler):
    def usability(self, holding):
        return USABLE if self.ctx.table.environment else unusable("No environment rule is in force.")

    def targets(self, holding):
        return tuple(ChoiceOption(r.id, r.label, r.help) for r in self.ctx.table.rule_views())

    def prompt(self):
        return "Choose an environment rule to remove for good."

    def apply(self, holding, target):
        name = self.ctx.table.remove_rule(target)
        return f"Clause Removal: {name} is gone."


# --- this round's preparations ---------------------------------------------------------------


class Preparation(ItemHandler):
    """Prepared effects (effects.py) last until this round settles; one of each per round."""

    def usability(self, holding):
        return unusable("Already prepared this round.") if self.ctx.prepared(self.id) else USABLE

    def apply(self, holding, target):
        self.ctx.prepare(self.id)
        return f"{PRODUCTS[self.id].name} is ready for this round."


@handler("ph_buffer")
class TemporaryAllowance(Preparation):
    pass


@handler("ph_silence")
class SilenceSeal(Preparation):
    def apply(self, holding, target):
        self.ctx.prepare(self.id)
        return "Silence Seal: no environment rule applies this round."


@handler("ph_quad")
class FourfoldTicket(Preparation):
    def usability(self, holding):
        prepared = super().usability(holding)
        if not prepared or self.ctx.betting:
            return prepared
        # Only a plain double must be covered; a fourfold loss beyond the cash becomes debt.
        return USABLE if self.ctx.can(Action.DOUBLE) else unusable("You cannot double now.")


@handler("ph_insurance")
class BustInsurance(Preparation):
    def apply(self, holding, target):
        self.ctx.prepare(self.id)
        return "Bust Insurance: if you bust this round, the dealer still plays; a dealer bust makes it a push."


@handler("ph_waiver")
class LossWaiver(Preparation):
    def usability(self, holding):
        return USABLE if self.ctx.can(Action.SURRENDER) else unusable("You cannot surrender now.")

    def apply(self, holding, target):
        self.ctx.prepare(self.id)
        return "Loss Waiver: you surrender without a loss."

    def after(self) -> None:
        self.ctx.surrender()


# --- money -----------------------------------------------------------------------------------


@handler("ph_buyback")
class OriginalPriceReceipt(ItemHandler):
    def usability(self, holding):
        return USABLE if self.targets(holding) else unusable("You hold no other purchased consumable.")

    def targets(self, holding):
        out = []
        for h in self.ctx.table.holdings.items:
            if h.uid == holding.uid or h.paid <= 0:
                continue
            row = product(h.id)
            out.append(ChoiceOption(h.uid, f"{row.name if row else h.id} ({h.paid} chips)",
                                    f"Return it for the {h.paid} chips you paid."))
        return tuple(out)

    def prompt(self):
        return "Choose a consumable to return for the price you paid."

    def apply(self, holding, target):
        returned = self.ctx.table.holdings.get(target)
        self.ctx.table.discard(returned)
        self.ctx.add_cash(returned.paid)
        row = product(returned.id)
        return f"Original Price Receipt: {row.name if row else returned.id} returned for {returned.paid} chips."
