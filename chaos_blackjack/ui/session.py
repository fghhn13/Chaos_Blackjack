"""Interactive CLI session — UX_design.md template."""

from __future__ import annotations

from dataclasses import dataclass
import random
import shlex
import sys
from typing import Callable, TextIO

from chaos_blackjack import auto_load_plugins
from chaos_blackjack.contracts.items import ItemResult
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.events.dispatcher import EventDispatcher
from chaos_blackjack.registry import get_registry
from chaos_blackjack.rules.rule_engine import RuleContext
from chaos_blackjack.core.run_state import (
    CardSnapshot,
    GameStateSnapshot,
    ModifierSnapshot,
    RunSaveData,
)
from chaos_blackjack.core.save_manager import save_game
from chaos_blackjack.logic.run_end_policy import (
    CompositeRunEndPolicy,
    MoneyBankruptDefeatPolicy,
    MoneyTargetVictoryPolicy,
)
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.ui.descriptions import chaos_ai_flavor, describe_active_modifiers, info_rules_text
from chaos_blackjack.ui.feedback import FeedbackLog
from chaos_blackjack.ui.formatting import format_dealer_visible, format_hand


def _inventory_counts(inventory: tuple[str, ...]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for x in inventory:
        counts[x] = counts.get(x, 0) + 1
    return sorted(counts.items())


def _remove_one(inv: tuple[str, ...], item_id: str) -> tuple[str, ...]:
    lst = list(inv)
    if item_id in lst:
        lst.remove(item_id)
    return tuple(lst)


MVP_START_MONEY = 100
MVP_TARGET_MONEY = 400
MVP_REWARD_STREAK = 2
MVP_DEFAULT_REWARD_POOL: tuple[str, ...] = ("peek", "shield", "swap")


@dataclass
class RunState:
    money: int
    start_money: int
    round: int
    target_money: int
    objective: str
    win_streak: int
    current_bet: int
    items: tuple[str, ...]


def _card_to_snapshot(card: Card) -> CardSnapshot:
    return CardSnapshot(rank=str(card.rank), suit=str(card.suit or ""))


def _snapshot_to_card(s: CardSnapshot) -> Card:
    return Card(Rank(s.rank), s.suit)


def _game_state_to_snapshot(state: GameState) -> GameStateSnapshot:
    return GameStateSnapshot(
        player_hand=[_card_to_snapshot(c) for c in state.player_hand],
        dealer_hand=[_card_to_snapshot(c) for c in state.dealer_hand],
        deck=[_card_to_snapshot(c) for c in state.deck],
        phase=state.phase.name,
        chaos_budget_remaining=int(state.chaos_budget_remaining),
        inventory=list(state.inventory),
    )


def _snapshot_to_game_state(s: GameStateSnapshot) -> GameState:
    return GameState(
        player_hand=tuple(_snapshot_to_card(c) for c in s.player_hand),
        dealer_hand=tuple(_snapshot_to_card(c) for c in s.dealer_hand),
        deck=tuple(_snapshot_to_card(c) for c in s.deck),
        phase=GamePhase[s.phase],
        chaos_budget_remaining=int(s.chaos_budget_remaining),
        inventory=tuple(s.inventory),
    )


def _serialize_modifier_params(mod: object) -> dict[str, object]:
    # Generic heuristics for current modifier plugins.
    params: dict[str, object] = {}
    if hasattr(mod, "delta"):
        try:
            params["delta"] = int(getattr(mod, "delta"))
        except Exception:
            pass

    mid = getattr(mod, "id", None)
    if mid == "tiebreaker_shift" and hasattr(mod, "chaos_flags"):
        flags = getattr(mod, "chaos_flags") or frozenset()
        ties_to = "dealer" if "dealer_wins_ties" in flags else "player"
        params["ties_to"] = ties_to

    return params


def _serialize_active_modifiers(loop: GameLoop) -> list[ModifierSnapshot]:
    out: list[ModifierSnapshot] = []
    for m in loop.modifiers.items:
        mid = getattr(m, "id", None)
        if not mid:
            continue
        params = _serialize_modifier_params(m)
        out.append(ModifierSnapshot(id=str(mid), params=params))
    return out


def _deserialize_active_modifiers(
    mods: list[ModifierSnapshot],
    *,
    registry,
) -> ActiveModifiers:
    built: list[object] = []
    for m in mods:
        inst = registry.build_chaos_rule(m.id, m.params)
        if inst is None:
            raise ValueError(f"Unknown chaos rule id in save: {m.id}")
        built.append(inst)
    return ActiveModifiers(items=tuple(built))


def _build_save_data(
    *,
    run: RunState,
    state: GameState,
    loop: GameLoop,
    enable_chaos: bool,
) -> RunSaveData:
    active = _serialize_active_modifiers(loop)
    chaos_actions_this_turn = int(getattr(loop, "_chaos_actions_this_turn", 0))

    return RunSaveData(
        version=1,
        money=run.money,
        start_money=run.start_money,
        round=run.round,
        items=list(state.inventory),
        objective=run.objective,
        win_streak=run.win_streak,
        target_money=run.target_money,
        current_bet=run.current_bet,
        enable_chaos=bool(enable_chaos),
        game_state=_game_state_to_snapshot(state),
        active_modifiers=active,
        chaos_actions_this_turn=chaos_actions_this_turn,
    )


def run_interactive_session(
    *,
    seed: int | None = None,
    enable_chaos: bool = False,
    start_money: int = MVP_START_MONEY,
    target_money: int = MVP_TARGET_MONEY,
    objective: str = "double_money",
    round_limit: int | None = None,
    reward_pool: tuple[str, ...] = MVP_DEFAULT_REWARD_POOL,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    auto_load_plugins()
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    log = FeedbackLog()
    dispatcher = EventDispatcher()
    log.wire_dispatcher(dispatcher.register)

    loop = GameLoop(dispatcher=dispatcher)
    loop.initial_inventory = ()
    rng = random.Random(seed) if seed is not None else random.Random()
    run_end_policy = CompositeRunEndPolicy(
        policies=(MoneyBankruptDefeatPolicy(), MoneyTargetVictoryPolicy()),
    )
    run = RunState(
        money=start_money,
        start_money=start_money,
        round=1,
        target_money=target_money,
        objective=objective,
        win_streak=0,
        current_bet=0,
        items=loop.initial_inventory,
    )

    def read_line(prompt: str = "") -> str:
        stdout.write(prompt)
        stdout.flush()
        return stdin.readline()

    while True:
        min_bet, max_bet = _bet_limits(run.money)
        if max_bet < min_bet:
            stdout.write(
                "\nYou no longer have enough bankroll to place a valid bet.\n"
                "Game Over.\n"
            )
            return

        run.current_bet = _prompt_bet(
            read_line=read_line,
            stdout=stdout,
            money=run.money,
        )
        st = loop.new_round(
            seed=rng.randint(0, 2**30),
            inventory_override=run.items,
        )
        turn = 0

        while st.phase == GamePhase.PLAYER_TURN:
            turn += 1
            if enable_chaos:
                st = loop.maybe_apply_chaos_phase(st)
            _render_screen(
                stdout,
                turn,
                st,
                loop,
                run=run,
                enable_chaos=enable_chaos,
                hide_dealer_hole=True,
            )
            pending = log.drain()
            if pending:
                stdout.write("\n--- Events ---\n")
                for line in pending:
                    stdout.write(line + "\n")

            st = _player_turn_loop(
                stdin,
                stdout,
                loop,
                log,
                st,
                turn,
                run,
                enable_chaos=enable_chaos,
            )
            if st.phase != GamePhase.PLAYER_TURN:
                break

        if st.phase == GamePhase.DEALER_TURN:
            st = _run_dealer_with_feedback(loop, log, st, stdout)

        pv = loop.rules.hand_value(st.player_hand, loop.context())
        dv = loop.rules.hand_value(st.dealer_hand, loop.context())
        out = loop.outcome_label(st)
        stdout.write("\n" + "=" * 30 + "\n")
        stdout.write("RESULT\n")
        stdout.write(f"Your hand: {format_hand(st.player_hand)}  → Total: {pv}\n")
        stdout.write(
            f"Dealer: {format_dealer_visible(st.dealer_hand, hide_hole=False)}  → Total: {dv}\n",
        )
        if loop.rules.is_bust(pv, loop.context()) and out == "dealer":
            stdout.write("💀 BUST!\n")
        elif out == "player":
            stdout.write("🏆 You win.\n")
        elif out == "dealer":
            stdout.write("House wins.\n")
        else:
            stdout.write("Push.\n")
        run.money = _settle_money(run.money, run.current_bet, out)
        run.items = st.inventory

        rewarded = _update_streak_and_maybe_reward(
            run=run,
            outcome=out,
            reward_pool=reward_pool,
            rng=rng,
        )

        stdout.write(f"Bet: {run.current_bet}\n")
        if out == "player":
            stdout.write(f"Round settlement: +{run.current_bet}\n")
        elif out == "dealer":
            stdout.write(f"Round settlement: -{run.current_bet}\n")
        else:
            stdout.write("Round settlement: +0\n")
        stdout.write(f"Bankroll: {run.money} / Target: {run.target_money}\n")
        stdout.write(f"Win streak: {run.win_streak}/{MVP_REWARD_STREAK}\n")
        if rewarded is not None:
            stdout.write(f"Reward earned: {rewarded}\n")
        stdout.write("=" * 30 + "\n")

        end = run_end_policy.check(run)
        if end is not None:
            stdout.write(f"\n{end.message}\n")
            return

        # Next round number (for save/load display and future objectives).
        run.round += 1


def run_interactive_session_from_save(
    data: RunSaveData,
    *,
    enable_chaos: bool = False,
    seed: int | None = None,
    reward_pool: tuple[str, ...] = MVP_DEFAULT_REWARD_POOL,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Resume an interactive game from a JSON save payload."""

    auto_load_plugins()
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout

    log = FeedbackLog()
    dispatcher = EventDispatcher()
    log.wire_dispatcher(dispatcher.register)

    loop = GameLoop(dispatcher=dispatcher)
    loop.initial_inventory = ()
    rng = random.Random(seed) if seed is not None else random.Random()

    run_end_policy = CompositeRunEndPolicy(
        policies=(MoneyBankruptDefeatPolicy(), MoneyTargetVictoryPolicy()),
    )

    effective_enable_chaos = bool(enable_chaos or data.enable_chaos)

    run = RunState(
        money=data.money,
        start_money=data.start_money,
        round=data.round,
        target_money=data.target_money,
        objective=data.objective,
        win_streak=data.win_streak,
        current_bet=data.current_bet,
        items=tuple(data.items),
    )

    # Restore current round snapshot (if present).
    st: GameState | None
    if data.game_state is not None:
        st = _snapshot_to_game_state(data.game_state)
    else:
        st = None

    # Restore active chaos modifiers / accounting.
    if st is not None and data.active_modifiers:
        reg = get_registry()
        loop.modifiers = _deserialize_active_modifiers(
            data.active_modifiers,
            registry=reg,
        )
        loop._chaos_actions_this_turn = int(data.chaos_actions_this_turn)
    elif st is not None:
        loop._chaos_actions_this_turn = int(data.chaos_actions_this_turn)

    # Force starting point: if no snapshot, begin a new round (prompt bet).
    if st is None:
        st = _start_new_round_with_bet(
            loop=loop,
            rng=rng,
        stdin=stdin,
            stdout=stdout,
            run=run,
        )

    while True:
        turn = 0
        while st.phase == GamePhase.PLAYER_TURN:
            turn += 1
            if effective_enable_chaos:
                st = loop.maybe_apply_chaos_phase(st)
            _render_screen(
                stdout,
                turn,
                st,
                loop,
                run,
                effective_enable_chaos,
                hide_dealer_hole=True,
            )
            pending = log.drain()
            if pending:
                stdout.write("\n--- Events ---\n")
                for line in pending:
                    stdout.write(line + "\n")
            st = _player_turn_loop(
                stdin,
                stdout,
                loop,
                log,
                st,
                turn,
                run,
                enable_chaos=effective_enable_chaos,
            )
            if st.phase != GamePhase.PLAYER_TURN:
                break

        if st.phase == GamePhase.DEALER_TURN:
            st = _run_dealer_with_feedback(loop, log, st, stdout)

        pv = loop.rules.hand_value(st.player_hand, loop.context())
        dv = loop.rules.hand_value(st.dealer_hand, loop.context())
        out = loop.outcome_label(st)
        stdout.write("\n" + "=" * 30 + "\n")
        stdout.write("RESULT\n")
        stdout.write(f"Your hand: {format_hand(st.player_hand)}  → Total: {pv}\n")
        stdout.write(
            f"Dealer: {format_dealer_visible(st.dealer_hand, hide_hole=False)}  → Total: {dv}\n",
        )
        if loop.rules.is_bust(pv, loop.context()) and out == "dealer":
            stdout.write("💀 BUST!\n")
        elif out == "player":
            stdout.write("🏆 You win.\n")
        elif out == "dealer":
            stdout.write("House wins.\n")
        else:
            stdout.write("Push.\n")

        run.money = _settle_money(run.money, run.current_bet, out)
        run.items = st.inventory

        rewarded = _update_streak_and_maybe_reward(
            run=run,
            outcome=out,
            reward_pool=reward_pool,
            rng=rng,
        )

        stdout.write(f"Bet: {run.current_bet}\n")
        if out == "player":
            stdout.write(f"Round settlement: +{run.current_bet}\n")
        elif out == "dealer":
            stdout.write(f"Round settlement: -{run.current_bet}\n")
        else:
            stdout.write("Round settlement: +0\n")
        stdout.write(f"Bankroll: {run.money} / Target: {run.target_money}\n")
        stdout.write(f"Win streak: {run.win_streak}/{MVP_REWARD_STREAK}\n")
        if rewarded is not None:
            stdout.write(f"Reward earned: {rewarded}\n")
        stdout.write("=" * 30 + "\n")

        end = run_end_policy.check(run)
        if end is not None:
            stdout.write(f"\n{end.message}\n")
            return

        run.round += 1
        st = _start_new_round_with_bet(
            loop=loop,
            rng=rng,
            stdin=stdin,
            stdout=stdout,
            run=run,
        )



def _render_screen(
    stdout: TextIO,
    turn: int,
    state: GameState,
    loop: GameLoop,
    run: RunState,
    enable_chaos: bool,
    *,
    hide_dealer_hole: bool,
) -> None:
    ctx: RuleContext = loop.context()
    pv = loop.rules.hand_value(state.player_hand, ctx)
    stdout.write("\n")
    stdout.write("=" * 30 + "\n")
    stdout.write("🃏 Chaos Blackjack\n")
    stdout.write("=" * 30 + "\n")
    stdout.write(f"Turn: {turn}\n\n")
    stdout.write(
        f"Bankroll: {run.money}  Target: {run.target_money}  Bet: {run.current_bet}\n",
    )
    stdout.write(f"Round: {run.round}  Objective: {run.objective}\n")
    stdout.write(f"Win streak: {run.win_streak}/{MVP_REWARD_STREAK}\n\n")
    stdout.write("Your Hand:\n")
    stdout.write(f"  {format_hand(state.player_hand)}  → Total: {pv}\n\n")
    stdout.write("Dealer:\n")
    stdout.write(f"  {format_dealer_visible(state.dealer_hand, hide_hole=hide_dealer_hole)}\n\n")
    stdout.write("-" * 30 + "\n")
    if enable_chaos:
        stdout.write("🤖 Chaos AI Active:\n")
        narration = getattr(loop, "last_chaos_narration", None)
        if narration:
            stdout.write(f'"{narration}"\n\n')
        else:
            stdout.write(f'"{chaos_ai_flavor(len(loop.modifiers.items))}"\n\n')
        stdout.write("⚡ Active Effects:\n")
        for line in describe_active_modifiers(loop.modifiers):
            stdout.write(f"- {line} (this round)\n")
        stdout.write(f"- Chaos budget remaining: {state.chaos_budget_remaining}\n")
    else:
        stdout.write("🤖 Chaos AI: disabled for MVP v1 run mode.\n")
    stdout.write("-" * 30 + "\n")
    stdout.write("🎒 Items:\n")
    counts = _inventory_counts(state.inventory)
    if not counts:
        stdout.write("  (empty)\n")
    else:
        for i, (name, n) in enumerate(counts, 1):
            stdout.write(f"  {i}. {name} ({n} use{'s' if n != 1 else ''})\n")
    stdout.write("\nAvailable Actions:\n")
    stdout.write("  1. Hit\n  2. Stand\n  3. Use Item\n")
    stdout.write("\nCommands:\n")
    stdout.write(
        "  info   → current rules\n"
        "  ai     → chaos flavor\n"
        "  items  → inventory\n"
        "  save   → save game (JSON)\n"
        "  debug state | debug rules\n"
        "  quit   → exit\n",
    )
    stdout.write("\n> ")


def _player_turn_loop(
    stdin: TextIO,
    stdout: TextIO,
    loop: GameLoop,
    log: FeedbackLog,
    state: GameState,
    turn: int,
    run: RunState,
    *,
    enable_chaos: bool,
) -> GameState:
    st = state
    while st.phase == GamePhase.PLAYER_TURN:
        raw = stdin.readline()
        if not raw:
            return st.with_phase(GamePhase.RESOLVED)
        parts = shlex.split(raw.strip(), posix=False)
        if not parts:
            stdout.write("> ")
            continue
        cmd = parts[0].lower()

        if cmd == "save":
            stdout.write("\nEnter save name:\n> ")
            name = stdin.readline()
            if not name:
                stdout.write("\nSave cancelled.\n\n> ")
                continue
            name = name.strip()
            data = _build_save_data(
                run=run,
                state=st,
                loop=loop,
                enable_chaos=enable_chaos,
            )
            save_game(data, name=name or "save_1.json")
            stdout.write("Game saved successfully.\n\n> ")
            continue

        if cmd in ("quit", "q", "exit"):
            stdout.write("Goodbye.\n")
            raise SystemExit(0)

        if cmd == "info":
            if enable_chaos:
                stdout.write("\n" + info_rules_text(loop.modifiers) + "\n\n> ")
            else:
                stdout.write("\nChaos is disabled in MVP v1 mode.\n\n> ")
            continue

        if cmd == "ai":
            if enable_chaos:
                stdout.write("\n🤖 Chaos AI:\n")
                narration = getattr(loop, "last_chaos_narration", None)
                if narration:
                    stdout.write(f'"{narration}"\n\n> ')
                else:
                    stdout.write(
                        f'"{chaos_ai_flavor(len(loop.modifiers.items))}"\n\n> ',
                    )
            else:
                stdout.write("\nChaos is disabled in MVP v1 mode.\n\n> ")
            continue

        if cmd == "items":
            stdout.write("\n🎒 Inventory detail:\n")
            for name, n in _inventory_counts(st.inventory):
                stdout.write(f"  - {name}: {n}\n")
            stdout.write("\n> ")
            continue

        if cmd == "debug" and len(parts) > 1:
            sub = parts[1].lower()
            if sub == "state":
                stdout.write(
                    f"\ndebug state: phase={st.phase.name} "
                    f"deck={len(st.deck)} inventory={list(st.inventory)}\n\n> ",
                )
            elif sub == "rules":
                stdout.write(
                    f"\ndebug rules: modifiers={len(loop.modifiers.items)} "
                    f"{[getattr(m,'id', '?') for m in loop.modifiers.items]}\n\n> ",
                )
            else:
                stdout.write("\nUsage: debug state | debug rules\n\n> ")
            continue
        if cmd == "debug":
            stdout.write("\nUsage: debug state | debug rules\n\n> ")
            continue

        if cmd in ("1", "hit", "h"):
            st = loop.draw_for_player(st)
            pv = loop.rules.hand_value(st.player_hand, loop.context())
            for line in log.drain():
                stdout.write("\n" + line)
            stdout.write(f"\nNew Total: {pv}\n")
            if loop.rules.is_bust(pv, loop.context()):
                stdout.write("💀 BUST!\n")
                return st.with_phase(GamePhase.RESOLVED)
            _render_screen(
                stdout,
                turn + 1,
                st,
                loop,
                run=run,
                enable_chaos=enable_chaos,
                hide_dealer_hole=True,
            )
            for line in log.drain():
                stdout.write(line + "\n")
            continue

        if cmd in ("2", "stand", "s"):
            return st.with_phase(GamePhase.DEALER_TURN)

        if cmd in ("3", "use", "item"):
            st = _use_item_menu(stdin, stdout, loop, log, st)
            if st.phase != GamePhase.PLAYER_TURN:
                return st
            _render_screen(
                stdout,
                turn,
                st,
                loop,
                run=run,
                enable_chaos=enable_chaos,
                hide_dealer_hole=True,
            )
            continue

        stdout.write("Unknown input. Try 1/2/3 or info/quit.\n> ")

    return st


def _use_item_menu(
    stdin: TextIO,
    stdout: TextIO,
    loop: GameLoop,
    log: FeedbackLog,
    state: GameState,
) -> GameState:
    inv_unique = sorted(set(state.inventory))
    if not inv_unique:
        stdout.write("\nNo items to use.\n\n> ")
        return state
    stdout.write("\nChoose Item:\n")
    for i, name in enumerate(inv_unique, 1):
        stdout.write(f"  {i}. {name}\n")
    stdout.write("  0. Cancel\n> ")
    line = stdin.readline()
    if not line:
        return state
    choice = line.strip()
    if choice == "0":
        return state
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(inv_unique):
            item_id = inv_unique[idx]
            return _apply_item_use(stdout, loop, log, state, item_id)
    except ValueError:
        pass
    stdout.write("Cancelled.\n\n> ")
    return state


def _apply_item_use(
    stdout: TextIO,
    loop: GameLoop,
    log: FeedbackLog,
    state: GameState,
    item_id: str,
) -> GameState:
    from chaos_blackjack.contracts.items import ItemContext

    reg = get_registry()
    cls = reg.resolve_item(item_id)
    if cls is None:
        stdout.write(f"\nUnknown item: {item_id}\n\n> ")
        return state
    if item_id not in state.inventory:
        stdout.write("\nYou don't have that item.\n\n> ")
        return state

    ctx = ItemContext(
        state,
        emit_event=loop.emit_event,
        peek_next_card_rank=lambda: state.deck[0].rank if state.deck else None,
    )
    inst = cls()
    result = inst.use(ctx)
    stdout.write("\n")
    for line in log.drain():
        stdout.write(line + "\n")
    if result.ok:
        state_after_effect = _apply_item_effects(state, result)
        new_inv = _remove_one(state_after_effect.inventory, item_id)
        stdout.write(f"{result.message}\n\n> ")
        return state_after_effect.with_inventory(new_inv)
    stdout.write(f"{result.message}\n\n> ")
    return state


def _apply_item_effects(state: GameState, result: ItemResult) -> GameState:
    extra = result.extra if isinstance(result.extra, dict) else {}
    if not extra.get("swap_top_into_first_player_card"):
        return state
    if not state.player_hand or not state.deck:
        return state
    top, *rest = state.deck
    player = state.player_hand
    swapped = (top,) + player[1:]
    return state.with_player_hand(swapped).with_deck(tuple(rest))


def _bet_limits(money: int) -> tuple[int, int]:
    return (1, money // 2)


def _prompt_bet(
    *,
    read_line: Callable[[str], str],
    stdout: TextIO,
    money: int,
) -> int:
    min_bet, max_bet = _bet_limits(money)
    while True:
        raw = read_line(f"\nMoney: {money}\nEnter bet ({min_bet}~{max_bet}): ")
        if not raw:
            raise SystemExit(0)
        raw = raw.strip()
        try:
            bet = int(raw)
        except ValueError:
            stdout.write("Bet must be an integer.\n")
            continue
        if bet < min_bet or bet > max_bet:
            stdout.write(f"Invalid bet. Allowed range: {min_bet}~{max_bet}\n")
            continue
        return bet


def _start_new_round_with_bet(
    *,
    loop: GameLoop,
    rng: random.Random,
    stdin: TextIO,
    stdout: TextIO,
    run: RunState,
) -> GameState:
    min_bet, max_bet = _bet_limits(run.money)
    if max_bet < min_bet:
        stdout.write(
            "\nYou no longer have enough bankroll to place a valid bet.\n"
            "Game Over.\n"
        )
        raise SystemExit(0)

    def read_line(prompt: str = "") -> str:
        stdout.write(prompt)
        stdout.flush()
        return stdin.readline()

    run.current_bet = _prompt_bet(
        read_line=read_line,
        stdout=stdout,
        money=run.money,
    )
    return loop.new_round(
        seed=rng.randint(0, 2**30),
        inventory_override=run.items,
    )


def _settle_money(money: int, bet: int, outcome: str) -> int:
    if outcome == "player":
        return money + bet
    if outcome == "dealer":
        return money - bet
    return money


def _update_streak_and_maybe_reward(
    *,
    run: RunState,
    outcome: str,
    reward_pool: tuple[str, ...],
    rng: random.Random,
) -> str | None:
    if outcome == "player":
        run.win_streak += 1
        if run.win_streak >= MVP_REWARD_STREAK and reward_pool:
            reward = rng.choice(reward_pool)
            run.items = run.items + (reward,)
            run.win_streak = 0
            return reward
        return None
    run.win_streak = 0
    return None


def _run_dealer_with_feedback(
    loop: GameLoop,
    log: FeedbackLog,
    state: GameState,
    stdout: TextIO,
) -> GameState:
    s = state
    stdout.write("\n--- Dealer plays ---\n")
    while s.phase == GamePhase.DEALER_TURN:
        dv = loop.rules.hand_value(s.dealer_hand, loop.context())
        if loop.rules.is_bust(dv, loop.context()):
            stdout.write("Dealer busts.\n")
            return s.with_phase(GamePhase.RESOLVED)
        if dv >= 17:
            stdout.write(f"Dealer stands at {dv}.\n")
            return s.with_phase(GamePhase.RESOLVED)
        s = loop.draw_for_dealer(s)
        for line in log.drain():
            stdout.write(line + "\n")
    return s.with_phase(GamePhase.RESOLVED)
