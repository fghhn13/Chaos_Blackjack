"""Player-facing build references, evaluated against the selected balance profile."""

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.poker_head.catalog import PRODUCTS


STYLE_LABELS = {"long": "Multi-card", "retreat": "Surrender", "exact": "Precision",
                "double": "Double", "finance": "Finance", "common": "General"}
CATEGORY_LABELS = {"core": "Core", "permanent": "Permanent", "item": "Consumable", "finance": "Finance"}

_FLAVOR = {
    "margin": "Leave yourself a little room at the edge.",
    "retreat": "A graceful exit keeps your next hand alive.",
    "approx": "Close enough can be perfect.",
    "redeal": "Not this hand. The next one.",
    "stakes": "A bigger commitment deserves a bigger reward.",
    "account": "Your seat now comes with a private account.",
    "long_reward": "Every extra card can earn its keep.",
    "court": "Even royalty can offer a concession.",
    "five_reward": "Make room for one more guest at the feast.",
    "mark": "A discreet mark points to what comes next.",
    "late_retreat": "The exit stays open a little longer.",
    "loss_discount": "Negotiate the price of walking away.",
    "claim": "Keep the receipt. Your comeback may cover it.",
    "ace": "Your next opening has an ace up its sleeve.",
    "jackpot": "Perfect timing earns a generous payout.",
    "sleeve": "A spare card can change the shape of a hand.",
    "borrow": "Let the dealer's perfect opening become your good fortune.",
    "late_double": "There is still time to raise the stakes.",
    "risk": "Someone else carries part of the risk.",
    "audit": "A heavy hidden card deserves a closer look.",
    "discount": "A preferred customer pays a little less.",
    "yield": "Give a successful investment a little extra lift.",
    "refresh": "One more look at the exchange, on the house.",
    "gift": "Choose the terms of your invitation.",
    "change": "A new agreement can reshape the rest of your run.",
    "peek": "Focus on the next card.",
    "swap": "Trade an awkward opening for another chance.",
    "hole": "Bring the dealer's secret into the light.",
    "radar": "Check the danger before taking another step.",
    "oracle": "See your hand before committing your chips.",
    "insurance": "Even a bust can still be saved.",
    "remove": "Cross out a clause you can do without.",
    "silence": "For one hand, let the cards speak alone.",
    "buffer": "A temporary allowance gives your hand more room.",
    "waiver": "Leave the table with this wager intact.",
    "aces": "Bring an ace to the front.",
    "undo": "Recall the last card before it defines your hand.",
    "quad": "One ticket. Four times the commitment.",
    "buyback": "A purchase can become cash again.",
    "deposit": "Give your chips time to earn a return.",
    "bond": "Back your own performance with a contract.",
    "stock": "A risky position promises an uncertain return.",
    "loan": "Borrow time now; settle the account later.",
}

_LIMITS = {
    "margin": "Changes only your bust ceiling. The dealer and Chaos rules keep their own effects.",
    "redeal": "A table action during your turn while you still hold exactly your two opening cards. The old cards are gone; the two new ones come from the top of the deck, so a revealed next card moves too. Not a natural: a new 21 is just 21.",
    "approx": "Applies after opening natural settlement, before your bust check. It neither creates a natural nor automatically wins or stands. A Chaos ceiling below 21 can still make the recognized 21 bust.",
    "stakes": "Requires a winning doubled hand. The bonus uses the final wager, including a Fourfold Ticket.",
    "account": "Financial products are offered only while this core is active. Existing contracts remain in force after changing cores.",
    "long_reward": "Requires a win; a push or surrender earns no card-count bonus. Adds to other winning bonuses.",
    "court": "Your J/Q/K switch like aces: their effective value, or 5 while that keeps the hand from busting. Only your cards change; the dealer's face cards keep their effective values.",
    "five_reward": "Requires a win; reaching the card count alone does not settle the hand. Adds to Long Hand Dividend.",
    "mark": "Reveals a rank once when your turn begins. It does not update after you draw or reorder the deck.",
    "late_retreat": "You must still be in your turn and not have busted. An item use does not restore a finished hand.",
    "claim": "Only a paid surrender creates a receipt. It expires after the next round, cannot stack, and is lost if replaced. Loss Waiver creates no receipt.",
    "ace": "Changes the first opening card to an ace of the same suit in the next round. An ace plus a ten-value opening card can be a natural. Replacing this permanent clears the pending ace.",
    "jackpot": "This is base profit, not an extra payout on top of normal win profit. Other eligible bonuses add to it. Opening naturals and Borrowed Glory also qualify.",
    "sleeve": "Once per round. Replaces the first card, not a card of your choice; the discarded card does not return to the deck.",
    "borrow": "Uses the dealer's original two-card natural, including when both hands are natural. It changes the outcome without exchanging hands or manufacturing a 21-point hand.",
    "late_double": "The final wager must be affordable. Double still draws exactly one card and ends your turn.",
    "risk": "Applies to a doubled loss, including Fourfold Ticket. Does not discount surrender or ordinary losses; the charge rounds upward.",
    "audit": "Checks the dealer's effective hole-card value, including a high ace, when your turn begins. A smaller hole card remains hidden.",
    "discount": "Prices round upward. Investments and loans are excluded. Original Price Receipt refunds what you actually paid.",
    "yield": "Must be equipped at maturity. Applies only to positive profit, rounded down, without multiplying principal or reducing a loss.",
    "refresh": "One additional free refresh per stock. Replacing and re-equipping it does not restore a used refresh.",
    "gift": "Free at the beginning of the run. Taking cash means no core for the entire run and disables Amendment Letter.",
    "change": "Choices are fixed when purchased and exclude your current core. Purchased goods and contracts remain; the new core changes shop style weighting.",
    "peek": "Reveals the next rank, without drawing or revealing its suit.",
    "swap": "Replaces your first card with the next deck card. The old card is discarded.",
    "hole": "Reveals the hole card without changing it or the dealer's hand.",
    "radar": "Uses your effective values, bust ceiling, core and temporary effects at the time of use.",
    "oracle": "Shows your two opening cards, including suits, before you bet (a pending Comeback Ace already turns the first into an ace). Does not show the dealer's cards. Forecasts survive saves and shopping; card effects during your turn can make them outdated.",
    "insurance": "Prepare it before betting or during your turn, before you bust. If you then bust, the dealer plays out: a dealer bust makes the round a push, otherwise you lose as usual. An environment rule that already changes your bust wins first.",
    "remove": "Choose one active persistent rule. Removal lasts for the run; the dealer may introduce that rule again later.",
    "silence": "Includes any new rule introduced this round. Suppressed rules return next round. Cannot be used twice in one round.",
    "buffer": "Only your ceiling changes. Once per round; can be prepared before betting and expires after settlement.",
    "waiver": "Requires legal surrender. Creates no Recovery Receipt, but can trigger Comeback Ace.",
    "aces": "Moves only the first remaining ace; every other card keeps its order. Creates no new cards. Cannot be used when no ace remains or the next card is already an ace.",
    "undo": "At least two cards must remain. The recalled card is discarded rather than returned to the deck. Cannot rescue a hand that has already settled.",
    "quad": "Once per round. Changes the next legal double's wager multiplier; it does not allow a second double. Your cash only needs to cover a plain double; a loss beyond your cash becomes debt that counts against net assets.",
    "buyback": "Choose another purchased consumable instance. Consumes both items and refunds the target's actual paid price. Free items, cores, permanents and contracts are ineligible. Can immediately reach the victory target.",
}

# Explicit mechanical connections; not a prescribed loadout.
_RELATED = {
    "margin": ("court", "five_reward"), "retreat": ("loss_discount", "claim", "ace"),
    "approx": ("jackpot", "sleeve", "aces"), "stakes": ("risk", "quad", "audit"),
    "redeal": ("jackpot", "sleeve", "mark"),
    "account": ("deposit", "yield", "loan"), "long_reward": ("five_reward", "court"),
    "court": ("margin", "five_reward"), "five_reward": ("long_reward", "margin"),
    "mark": ("sleeve", "aces"), "late_retreat": ("retreat", "ace"),
    "loss_discount": ("retreat", "claim"), "claim": ("loss_discount", "waiver"),
    "ace": ("late_retreat", "waiver"), "jackpot": ("approx", "borrow"),
    "sleeve": ("approx", "mark"), "borrow": ("jackpot",),
    "late_double": ("quad", "audit"), "risk": ("stakes", "quad"),
    "audit": ("late_double", "stakes"), "discount": ("buyback", "refresh"),
    "yield": ("deposit", "bond", "stock"), "refresh": ("account", "discount"),
    "gift": ("change",), "change": ("gift",), "peek": ("sleeve", "five_reward"),
    "swap": ("approx", "mark"), "hole": ("retreat", "late_double"),
    "radar": ("margin", "buffer"), "oracle": ("quad", "aces"), "insurance": ("buffer", "five_reward"),
    "remove": ("silence",), "silence": ("remove",), "buffer": ("five_reward", "margin"),
    "waiver": ("ace", "claim"), "aces": ("approx", "mark"), "undo": ("approx", "jackpot"),
    "quad": ("stakes", "risk"), "buyback": ("discount",),
    "deposit": ("yield", "account"), "bond": ("yield", "jackpot"),
    "stock": ("yield", "account"), "loan": ("account", "quad"),
}


def effect(item_id: str, config: RunConfig) -> str:
    """Render tunable effects from the supplied config, with profile defaults for old configs."""
    key = item_id.removeprefix("ph_")
    defaults = RunConfig()
    settings = {**defaults.mode_settings, **config.mode_settings}
    params = {**defaults.item_params.get(item_id, {}), **config.item_params.get(item_id, {})}
    s = lambda name: settings["chaos." + name]
    if key == "margin": return f"Raise your bust limit by {s('margin_bonus')} while this core is active."
    if key == "retreat": return f"Surrender loses only {s('surrender_pct')}% of your wager, rounded upward."
    if key == "approx": return f"After opening natural settlement, your totals of {str(s('approx_values')).replace(',', ' and ')} count as 21."
    if key == "stakes": return f"A doubled win earns an extra {s('double_bonus_pct')}% of the final wager."
    if key == "account": return f"Add {s('extra_shop_slots')} shop slot(s) and unlock financial products."
    if key in ("long_reward", "five_reward"): return f"Win with at least {params['cards']} cards for an extra {params['bonus_pct']}% of the final wager."
    if key == "court": return f"Your J, Q and K count as 10 or {params['value']}, whichever is better (like an ace)."
    if key == "loss_discount": return f"Reduce surrender loss by {params['discount_pct']} percentage points, to a minimum of {params['minimum_pct']}%."
    if key == "claim": return f"After a paid surrender, win the next round to recover {s('base_surrender_pct')}% of the surrendered wager, rounded upward, regardless of its discounted loss."
    if key == "jackpot": return f"A winning recognized 21 earns base profit of {params['multiplier']} times the final wager."
    if key == "risk": return f"On a doubled loss, pay only {100 - params['discount_pct']}% of the final wager, rounded upward."
    if key == "audit": return f"When your turn starts, reveal a dealer hole card with effective value at least {params['threshold']}."
    if key == "discount": return f"Shop goods cost {params['discount_pct']}% less; prices round upward."
    if key == "yield": return f"Positive investment profit increases by {params['bonus_pct']}% at maturity."
    if key == "gift": return f"Choose one of two random cores, or take {s('decline_cash')} chips and no core for this run."
    if key == "buffer": return f"Raise your bust limit by {params['bonus']} for this round."
    if key == "quad": return f"Your next legal double this round stakes {params['multiplier']} times the original wager; a loss beyond your cash becomes debt."
    if key == "deposit": return f"Invest {config.shop_prices.get(item_id, defaults.shop_prices[item_id])} chips; receive {params['payout']} after {params['rounds']} rounds."
    if key == "bond": return f"Invest {config.shop_prices.get(item_id, defaults.shop_prices[item_id])} chips; win at least {params['wins']} of {params['rounds']} rounds to receive {params['payout']}, otherwise {params['failure']}."
    if key == "stock": return f"Invest {config.shop_prices.get(item_id, defaults.shop_prices[item_id])} chips; after {params['rounds']} rounds, a {params['probability'] * 100:g}% chance of {params['payout']}, otherwise 0."
    if key == "loan": return f"Receive {params['advance']} chips now; repay {params['repay']} after {params['rounds']} rounds. One loan at a time."
    return PRODUCTS[item_id].description


def timing(item_id: str) -> str:
    p = PRODUCTS[item_id]
    if p.phases == "BP": return "Before bet / Your turn"
    if p.phases == "B": return "Before betting"
    if p.phases == "P": return "Your turn"
    if p.kind == "finance": return "Buy before betting"
    return "Automatic while equipped" if p.kind == "permanent" else "While active"


def price_label(item_id: str, config: RunConfig) -> str:
    p = PRODUCTS[item_id]
    if p.kind == "core": return "Invitation choice"
    if item_id == "ph_gift": return "Free opening gift"
    if item_id == "ph_loan":
        params = {**RunConfig().item_params[item_id], **config.item_params.get(item_id, {})}
        return f"Borrow {params['advance']} / Repay {params['repay']}"
    price = config.shop_prices.get(item_id)
    if price is None: return "Not stocked in this profile"
    return f"Invest {price} chips" if p.kind == "finance" else f"{price} chips"


def related(item_id: str) -> tuple[str, ...]:
    return tuple("ph_" + key for key in _RELATED.get(item_id.removeprefix("ph_"), ()))


def detail(item_id: str, config: RunConfig) -> str:
    p = PRODUCTS[item_id]
    key = item_id.removeprefix("ph_")
    paragraphs = [_FLAVOR[key], "Effect\n" + effect(item_id, config), "Timing\n" + timing(item_id)]
    limits = _LIMITS.get(key, "")
    if p.kind == "core":
        weight = config.mode_settings.get("chaos.style_weight", RunConfig().mode_settings["chaos.style_weight"])
        limits += f" One active core. Matching-style shop offers receive a {weight:g}x selection weight."
    if p.kind == "permanent":
        slots = config.mode_settings.get("chaos.build_slots", RunConfig().mode_settings["chaos.build_slots"])
        limits += f" Uses one of {slots} permanent slots. One copy per product; replace before betting without a refund."
    if p.kind == "item": limits += " A successful use consumes one copy."
    if p.kind == "finance":
        target = config.mode_settings.get("chaos.config.target_money", config.target_money)
        limits = ("Requires Private Account to buy. The purchase round counts toward maturity, including naturals, pushes and surrenders. "
                  "Net assets = cash + invested principal at cost - full outstanding loan repayment. "
                  f"Win at {target} net assets. On victory, principal and debt settle without unearned interest.")
        if key == "bond": limits += " Only actual player wins and natural wins count toward the contract."
        if key == "loan": limits += " Only one outstanding loan; no rollover. Borrowing increases cash and also creates debt."
    paragraphs.extend(["Limits\n" + limits.strip(), "Acquisition\n" + price_label(item_id, config)])
    if key == "claim":
        rate = config.mode_settings.get("chaos.base_surrender_pct", RunConfig().mode_settings["chaos.base_surrender_pct"])
        paragraphs.append(f"Example\nA 20-chip surrender records the wager. Win next round to recover {-(-20 * rate // 100)} chips even if a discount reduced your loss.")
    if key == "approx": paragraphs.append("Example\nA recognized 21 can still lose if the active Chaos bust ceiling is 19.")
    if key == "loan": paragraphs.append("Example\nThe advance is spendable cash, but the full repayment is deducted from net assets immediately.")
    links = related(item_id)
    if links: paragraphs.append("Related effects\n" + ", ".join(PRODUCTS[x].name for x in links))
    return "\n\n".join(paragraphs)
