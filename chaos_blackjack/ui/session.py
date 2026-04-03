"""Interactive CLI session — UX_design.md template."""

from __future__ import annotations

import random
import shlex
import sys
from typing import TextIO

from chaos_blackjack import auto_load_plugins
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import GamePhase, GameState
from chaos_blackjack.events.dispatcher import EventDispatcher
from chaos_blackjack.registry import get_registry
from chaos_blackjack.rules.rule_engine import RuleContext
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


def run_interactive_session(
    *,
    seed: int | None = None,
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
    rng = random.Random(seed) if seed is not None else random.Random()

    def read_line(prompt: str = "") -> str:
        stdout.write(prompt)
        stdout.flush()
        return stdin.readline()

    while True:
        st = loop.new_round(seed=rng.randint(0, 2**30))
        turn = 0

        while st.phase == GamePhase.PLAYER_TURN:
            turn += 1
            st = loop.apply_chaos_phase(st)
            _render_screen(stdout, turn, st, loop, hide_dealer_hole=True)
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
        stdout.write("=" * 30 + "\n")

        q = read_line("\nPlay again? [y/N]: ").strip().lower()
        if q not in ("y", "yes"):
            stdout.write("Goodbye.\n")
            return


def _render_screen(
    stdout: TextIO,
    turn: int,
    state: GameState,
    loop: GameLoop,
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
    stdout.write("Your Hand:\n")
    stdout.write(f"  {format_hand(state.player_hand)}  → Total: {pv}\n\n")
    stdout.write("Dealer:\n")
    stdout.write(f"  {format_dealer_visible(state.dealer_hand, hide_hole=hide_dealer_hole)}\n\n")
    stdout.write("-" * 30 + "\n")
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

        if cmd in ("quit", "q", "exit"):
            stdout.write("Goodbye.\n")
            raise SystemExit(0)

        if cmd == "info":
            stdout.write("\n" + info_rules_text(loop.modifiers) + "\n\n> ")
            continue

        if cmd == "ai":
            stdout.write("\n🤖 Chaos AI:\n")
            narration = getattr(loop, "last_chaos_narration", None)
            if narration:
                stdout.write(f'"{narration}"\n\n> ')
            else:
                stdout.write(
                    f'"{chaos_ai_flavor(len(loop.modifiers.items))}"\n\n> ',
                )
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
            _render_screen(stdout, turn + 1, st, loop, hide_dealer_hole=True)
            for line in log.drain():
                stdout.write(line + "\n")
            continue

        if cmd in ("2", "stand", "s"):
            return st.with_phase(GamePhase.DEALER_TURN)

        if cmd in ("3", "use", "item"):
            st = _use_item_menu(stdin, stdout, loop, log, st)
            if st.phase != GamePhase.PLAYER_TURN:
                return st
            _render_screen(stdout, turn, st, loop, hide_dealer_hole=True)
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
        new_inv = _remove_one(state.inventory, item_id)
        stdout.write(f"{result.message}\n\n> ")
        return state.with_inventory(new_inv)
    stdout.write(f"{result.message}\n\n> ")
    return state


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
