"""Full, private AI context; player-facing observations stay separate."""

from dataclasses import asdict
import json
from typing import TYPE_CHECKING

from chaos_blackjack.app.help_text import ITEM_HELP
from chaos_blackjack.app.item_use import inventory_counts
from chaos_blackjack.app.persistence import serialize_modifier_params
from chaos_blackjack.app.shop import rounds_until_restock
from chaos_blackjack.ui.descriptions import describe_modifier

if TYPE_CHECKING:
    from chaos_blackjack.app.controller import GameController


def build_chaos_context(controller: "GameController") -> str:
    c = controller
    st = c.state
    ctx = c.loop.context()
    constraints = c.loop.pipeline.action_constraints()
    allowed_rules = set(constraints["allowed_rules"])
    catalog = []
    for rule_id in constraints["allowed_rules"]:
        params = constraints["rule_params"].get(rule_id, {})
        modifier = c.loop.pipeline.registry.build_chaos_rule(rule_id, params)
        if modifier is not None:
            catalog.append({"id": rule_id, "fixed_params": params, "help": describe_modifier(modifier)})

    def cards(hand):
        return [f"{card.rank}{card.suit}" for card in hand]

    def hand(hand, actor="player"):
        context = c.loop.context(actor)
        total = c.loop.rules.hand_value(hand, context)
        if actor == "player" and c.table is not None and c.table.hidden_player_cards():
            # Face-down player cards stay hidden from the dealer's chat as well.
            hidden = c.table.hidden_player_cards()
            return {"cards": ["??" if i in hidden else f"{x.rank}{x.suit}" for i, x in enumerate(hand)],
                    "total": None, "bust": None}
        return {"cards": cards(hand), "total": total, "bust": c.loop.rules.is_bust(total, context)}

    data = {
        "phase": c.phase.value, "round": c.run.round,
        "bankroll": c.run.money, "start_money": c.run.start_money,
        "target": c.run.target_money, "objective": c.run.objective,
        "bet": c.run.current_bet, "win_streak": c.run.win_streak,
        "bet_range": c.bet_limits(), "doubled": c._doubled,
        "legal_actions": sorted(c._available_actions()),
        "player": hand(st.player_hand) if st else None,
        "dealer": hand(st.dealer_hand, "dealer") if st else None,
        "hole_revealed_to_player": c.hole_revealed,
        "deck": cards(st.deck) if st else [],
        "next_hit": hand(st.player_hand + st.deck[:1]) if st and st.deck else None,
        "inventory": [{"id": item, "count": count, "help": c.registry.describe_item(item)}
                      for item, count in inventory_counts(st.inventory if st else c.run.items)],
        "item_catalog": {item: c.registry.describe_item(item) for item in c.registry.item_ids()},
        "item_params": c.config.item_params,
        "shop": {"stock_round": c.shop.stock_round,
            "offers": [{"item": offer.item, "price": offer.price, "sold": offer.sold,
                        "affordable": not offer.sold and c.can_bet(c.run.money - offer.price)}
                       for offer in c.shop.offers],
            "restock_in": rounds_until_restock(
            c.shop, c.run.round, c.config.shop_refresh_rounds),
            "catalog_prices": c.config.shop_prices,
            "slots": c.config.shop_slots, "refresh_rounds": c.config.shop_refresh_rounds},
        "chaos": {"enabled": c.config.enable_chaos,
                  "budget": st.chaos_budget_remaining if st else c.loop.chaos_budget_initial,
                  "actions_this_turn": c.loop._chaos_actions_this_turn,
                  "permission_profile": {**c.loop.pipeline.permission_profile,
                                         "allowed_rules": constraints["allowed_rules"]},
                  "rule_params": constraints["rule_params"], "rule_catalog": catalog,
                  "rules": [{"id": str(getattr(mod, "id", "?")),
                             "params": {**constraints["rule_params"].get(getattr(mod, "id", ""), {}),
                                        **serialize_modifier_params(mod)}, "help": describe_modifier(mod)}
                            for mod in c.loop.modifiers.items if getattr(mod, "id", None) in allowed_rules]},
        "rules": {"dealer_stand_on": c.config.dealer_stand_on,
                  "blackjack_pays": c.config.blackjack_pays,
                  "balance_profile": c.config.balance_profile, "min_bet": c.config.min_bet,
                  "max_bet_fraction": c.config.max_bet_fraction,
                  "allow_double": c.config.allow_double, "allow_surrender": c.config.allow_surrender},
        "last_result": asdict(c.last_result) if c.last_result else None,
        "run_end": asdict(c.run_end) if c.run_end else None,
    }
    memory = c.chaos_memory.export()
    if memory is not None:
        data["memory"] = memory
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
