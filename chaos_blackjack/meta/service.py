"""MetaService — players, meta shop, runs and history on the game database.

Front-ends use the module-level functions in `chaos_blackjack.meta`, which
delegate to one service. Tests and GUI development can install a service on
an in-memory database (`chaos_blackjack.meta.fake`). Contracts:
docs/design/META_PROGRESSION.md §5.1 and docs/design/COSMETICS_ACHIEVEMENTS.md §6.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

from chaos_blackjack.achievements import achievements_catalog, get_achievement
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.cosmetics import COSMETIC_SLOTS, cosmetics, get_cosmetic
from chaos_blackjack.data.balance import Balance, BalanceError, MetaUpgradeBalance, default_balance, load_balance
from chaos_blackjack.data.db import MEMORY, connect, db_path
from chaos_blackjack.data.saves import SaveNotFound, load_run, save_run
from chaos_blackjack.meta import membership as tiers, onboarding, unlocks
from chaos_blackjack.meta.effects import get_effect
from chaos_blackjack.meta.models import (
    MAX_NAME_LENGTH, SLOTS, AchievementState, CosmeticOffer, MetaError, PendingRun, Player, PlayerSlot, PlayerStats,
    RunRecord, RunReward, RunStart, UpgradeOffer,
)
from chaos_blackjack.meta.table_log import TableLog
from chaos_blackjack.meta.tracker import RunTracker
from chaos_blackjack.modes import GameMode, get_mode, modes as all_modes

LoopFactory = Callable[[Any], Any]


@dataclass(frozen=True)
class ModeOption:
    mode: GameMode
    unlocked: bool
    hint: str = ""        # how to open a locked table (its silhouette shows this)


def consolation_tokens(balance: Balance, rounds: int, start: int, peak: int) -> list[tuple[str, int]]:
    """Breakdown of the tokens for a lost run (sums to at most meta.loss_cap)."""
    by_rounds = rounds * balance.meta_loss_per_round
    by_peak = max(0, peak - start) / max(1, start) * balance.meta_loss_per_peak_gain
    total = min(balance.meta_loss_cap, math.floor(by_rounds + by_peak))
    parts = [(f"Rounds survived ({rounds})", math.floor(by_rounds))]
    if by_peak >= 1:
        parts.append((f"Peak bankroll ({peak})", math.floor(by_peak)))
    raw = sum(t for _, t in parts)
    if raw > total:
        parts.append((f"Consolation cap ({balance.meta_loss_cap})", total - raw))
    return parts


def build_run_config(
    balance: Balance,
    mode: GameMode,
    owned: dict[str, int],
    consumables: Iterable[str] = (),
    *,
    seed: int | None = None,
) -> tuple[RunConfig, dict[str, int]]:
    """A run's config: profile + mode + every owned permanent upgrade + one copy
    of each listed consumable. Pure (no database); returns (config, applied).
    `owned` holds levels / copies; owned upgrades the profile no longer sells,
    and permanent upgrades of another mode, are skipped. Raises MetaError for
    consumables that cannot be brought (including those of another mode)."""
    catalog = {u.upgrade_id: u for u in balance.meta_upgrades}
    config = mode.apply(RunConfig.from_balance(balance, seed=seed))
    applied: dict[str, int] = {}
    for upgrade_id, level in sorted(owned.items()):
        u = catalog.get(upgrade_id)
        if u is None or u.kind != "permanent" or level < 1 or (u.mode and u.mode != mode.id):
            continue  # no longer sold in this profile, a consumable, or for another mode
        applied[upgrade_id] = min(level, u.max_level)
        config = _apply_upgrade(u, config, applied[upgrade_id])
    bring = list(consumables)
    kinds = len(set(bring))
    if kinds > config.bring_kinds:
        raise MetaError(f"You can bring up to {config.bring_kinds} kinds of items (Bag Space raises this)")
    for upgrade_id in bring:
        u = catalog.get(upgrade_id)
        if u is None or u.kind != "consumable":
            raise MetaError(f"{upgrade_id!r} is not a consumable you can bring")
        if u.mode and u.mode != mode.id:
            raise MetaError(f"{upgrade_id!r} can only be brought to {_mode_name(u.mode)}")
        if owned.get(upgrade_id, 0) < bring.count(upgrade_id):
            raise MetaError(f"You do not have enough {upgrade_id!r}")
        applied[upgrade_id] = applied.get(upgrade_id, 0) + 1
        config = _apply_upgrade(u, config, 1)
    return config.resolved(), applied  # an upgraded start moves a goal set as a multiple


def _mode_name(mode_id: str) -> str:
    try:
        return get_mode(mode_id).name
    except KeyError:
        return mode_id


def usable_in(u: MetaUpgradeBalance, mode_id: str) -> bool:
    """Whether an upgrade applies (permanent) or can be brought (consumable) in a mode."""
    return not u.mode or u.mode == mode_id


def reward_tokens(balance: Balance, result: str, rounds: int, start: int, peak: int, *,
                  chaos: bool = False) -> list[tuple[str, int]]:
    """Token breakdown for a finished run: the win reward (plus the Chaos
    bonus when Chaos was on), or the consolation."""
    if result == "victory":
        parts = [("Victory", balance.meta_win_tokens)]
        if chaos and balance.meta_chaos_win_bonus:
            parts.append(("Chaos bonus", balance.meta_chaos_win_bonus))
        return parts
    return consolation_tokens(balance, rounds, start, peak)


def _apply_upgrade(u: MetaUpgradeBalance, config: RunConfig, amount: int) -> RunConfig:
    try:
        effect = get_effect(u.effect)
    except KeyError as e:
        raise MetaError(f"Upgrade {u.upgrade_id} uses an effect this version does not have") from e
    return effect.apply(config, amount, dict(u.params))


class MetaService:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        """`conn` keeps one open connection (e.g. ":memory:"); None opens data/game.db per call."""
        self._conn = conn
        self._trackers: dict[int, RunTracker] = {}
        self._logs: dict[int, TableLog] = {}

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        if self._conn is not None:
            yield self._conn
            return
        conn = connect()
        try:
            yield conn
        finally:
            conn.close()

    # ---------------------------------------------------------------- players

    def list_slots(self) -> list[PlayerSlot]:
        with self._db() as db:
            ids = {r["slot"]: r["id"] for r in db.execute("SELECT id, slot FROM player")}
            return [PlayerSlot(s, self._player(db, ids[s]) if s in ids else None) for s in SLOTS]

    def create_player(self, slot: int, name: str) -> Player:
        if slot not in SLOTS:
            raise MetaError(f"Slot must be one of {SLOTS}")
        clean = _clean_name(name)
        with self._db() as db:
            try:
                start = self._balance(db, None, fallback=True).meta_vault_start
                with db:
                    pid = db.execute("INSERT INTO player (slot, name, tokens, guided) VALUES (?, ?, ?, ?)",
                                     (slot, clean, start, int(onboarding.guided_default()))).lastrowid
            except sqlite3.IntegrityError:
                raise MetaError(f"Slot {slot} is already used") from None
            return self._player(db, int(pid))

    def rename_player(self, player_id: int, name: str) -> Player:
        clean = _clean_name(name)
        with self._db() as db:
            self._player(db, player_id)
            with db:
                db.execute("UPDATE player SET name = ? WHERE id = ?", (clean, player_id))
            return self._player(db, player_id)

    def delete_player(self, player_id: int) -> None:
        with self._db() as db:
            self._player(db, player_id)
            with db:
                db.execute("DELETE FROM player WHERE id = ?", (player_id,))

    def get_player(self, player_id: int) -> Player:
        with self._db() as db:
            return self._player(db, player_id)

    def grant_tokens(self, player_id: int, amount: int) -> Player:
        """Development / testing helper: add (or remove) chips in the vault."""
        with self._db() as db:
            p = self._player(db, player_id)
            with db:
                db.execute("UPDATE player SET tokens = ? WHERE id = ?", (max(0, p.tokens + amount), player_id))
            return self._player(db, player_id)

    # ------------------------------------------------------------------- shop

    def meta_shop(self, player_id: int, profile: str | None = None) -> list[UpgradeOffer]:
        with self._db() as db:
            player = self._player(db, player_id)
            balance = self._balance(db, profile)
        return [self._offer(u, player) for u in balance.meta_upgrades]

    def buy_upgrade(self, player_id: int, upgrade_id: str, profile: str | None = None) -> Player:
        with self._db() as db:
            player = self._player(db, player_id)
            balance = self._balance(db, profile)
            upgrade = next((u for u in balance.meta_upgrades if u.upgrade_id == upgrade_id), None)
            if upgrade is None:
                raise MetaError(f"There is no upgrade {upgrade_id!r} for sale")
            offer = self._offer(upgrade, player)
            if not offer.can_buy:
                raise MetaError(offer.reason)
            with db:
                db.execute("UPDATE player SET tokens = tokens - ? WHERE id = ?", (offer.next_cost, player_id))
                db.execute(
                    "INSERT INTO player_upgrade (player_id, upgrade_id, amount) VALUES (?, ?, 1) "
                    "ON CONFLICT(player_id, upgrade_id) DO UPDATE SET amount = amount + 1",
                    (player_id, upgrade_id),
                )
            return self._player(db, player_id)

    def _offer(self, u: MetaUpgradeBalance, player: Player) -> UpgradeOffer:
        params = dict(u.params)
        owned = player.upgrades.get(u.upgrade_id, 0)
        try:
            effect = get_effect(u.effect)
            name, description = effect.title(params), effect.describe(params, 1)
        except KeyError:
            return UpgradeOffer(u.upgrade_id, u.upgrade_id, "", u.kind, owned, u.max_level, None, False,
                                "Not available in this version", u.mode)
        maxed = owned >= u.max_level
        cost = None if maxed else u.cost_of_level(owned + 1)
        if maxed:
            reason = "Maximum level" if u.kind == "permanent" else f"You can hold at most {u.max_level}"
        elif u.requires and player.upgrades.get(u.requires, 0) < 1:
            reason = f"Requires {u.requires}"
        elif cost is not None and player.tokens < cost:
            reason = f"Needs {cost} chips"
        else:
            reason = ""
        return UpgradeOffer(u.upgrade_id, name, description, u.kind, owned, u.max_level, cost, not reason, reason,
                            u.mode)

    # ------------------------------------------------------------------- runs

    # ----------------------------------------------------------------- vault

    def stake_range(self, mode_id: str, profile: str | None = None) -> tuple[int, int] | None:
        """(min, max) chips a run of this mode brings from the vault; None = a free table (no stake)."""
        with self._db() as db:
            return _stake_range(self._balance(db, profile), mode_id)

    def claim_relief(self, player_id: int, profile: str | None = None) -> int:
        """Poker Head tops up a vault that cannot cover Classic's minimum stake; returns the chips paid (0 if none)."""
        with self._db() as db:
            with db:
                return self._relief(db, player_id, self._balance(db, profile, fallback=True))

    def _relief(self, db: sqlite3.Connection, player_id: int, balance: Balance) -> int:
        stake = _stake_range(balance, "normal")
        if stake is None:
            return 0
        row = db.execute("SELECT tokens, relief_streak FROM player WHERE id = ?", (player_id,)).fetchone()
        if row is None or row["tokens"] >= stake[0]:
            return 0
        spend = db.execute("SELECT lifetime_spend FROM player WHERE id = ?", (player_id,)).fetchone()[0]
        grant = max(stake[0] - row["tokens"], min(tiers.relief_cap(balance, spend),
                                                    balance.meta_relief_base + balance.meta_relief_step * row["relief_streak"]))
        db.execute("UPDATE player SET tokens = tokens + ?, relief_streak = relief_streak + 1 WHERE id = ?",
                   (grant, player_id))
        return grant

    def membership(self, player_id: int, profile: str | None = None) -> "tiers.Membership":
        """The player's membership level from their lifetime spend."""
        with self._db() as db:
            player = self._player(db, player_id)
            return tiers.membership(self._balance(db, profile, fallback=True), player.lifetime_spend)

    def modes(self, player_id: int | None = None) -> list[ModeOption]:
        """The tables a player sees: open ones, and silhouettes of the next ones with how to open them
        (onboarding, docs/design/TUTORIAL.md); tables further along are not listed yet."""
        upgrades = self.get_player(player_id).upgrades if player_id is not None else {}
        reached = self.milestones(player_id) if player_id is not None else frozenset(onboarding.ALL)
        options = []
        for m in all_modes():
            if m.reveal is not None and m.reveal not in reached:
                continue
            if m.requires is not None and m.requires not in reached:
                options.append(ModeOption(m, False, m.teaser))
                continue
            bought = m.unlocked_by is None or upgrades.get(m.unlocked_by, 0) > 0
            options.append(ModeOption(m, bought, "" if bought else "Unlock it in the Shop"))
        return options

    # ---------------------------------------------------------------- onboarding

    def milestones(self, player_id: int) -> frozenset[str]:
        """Onboarding milestones the player has reached (all of them for a player from before onboarding)."""
        with self._db() as db:
            self._player(db, player_id)
            return onboarding.reached(db, player_id)

    def reach(self, player_id: int, milestone: str) -> bool:
        """Record an onboarding milestone (e.g. the tutorial finished); True when it is new."""
        with self._db() as db:
            self._player(db, player_id)
            try:
                with db:
                    return onboarding.reach(db, player_id, milestone)
            except ValueError as e:
                raise MetaError(str(e)) from None

    def start_run(
        self,
        player_id: int,
        mode_id: str,
        *,
        consumables: Iterable[str] = (),
        profile: str | None = None,
        seed: int | None = None,
        loop_factory: LoopFactory | None = None,
        stake: int | None = None,
        insure: bool = False,
    ) -> RunStart:
        """Build the run's config (profile + mode + upgrades), take the stake out of the vault (a mode with
        `mode.<id>.stake`; default: its minimum), use up the chosen consumables, record the run and return a
        tracked controller."""
        try:
            mode = get_mode(mode_id)
        except KeyError as e:
            raise MetaError(str(e)) from None
        bring = list(consumables)
        with self._db() as db:
            player = self._player(db, player_id)
            if mode.unlocked_by and player.upgrades.get(mode.unlocked_by, 0) < 1:
                raise MetaError(f"The {mode.name} mode is locked")
            reached = onboarding.reached(db, player_id)
            if mode.hidden or (mode.requires is not None and mode.requires not in reached):
                raise MetaError(f"{mode.name} is locked" + (f": {mode.teaser}" if mode.teaser else ""))
            balance = self._balance(db, profile)
            config, applied = build_run_config(balance, mode, player.upgrades, bring, seed=seed)
            notes: tuple[str, ...] = ()
            if mode.id == "normal" and onboarding.BET_CAP_LIFTED not in reached:
                config = replace(config, max_bet_fraction=min(config.max_bet_fraction, onboarding.CAP_FRACTION))
                notes = (f"For your first {onboarding.CAPPED_RUNS} runs here I cap each bet at a quarter of your "
                         "cash. Chips are not endless: throw them all on one hand and one bad card ends the run.",)
            bounds = _stake_range(balance, mode.id)
            if bounds is not None:
                lo, hi = bounds
                stake = lo if stake is None else int(stake)
                if player.tokens < lo:
                    raise MetaError(f"{mode.name} needs at least {lo} chips; you have {player.tokens}")
                if not lo <= stake <= min(hi, player.tokens):
                    raise MetaError(f"Bring {lo} to {min(hi, player.tokens)} chips to {mode.name}")
                config = replace(config, start_money=stake).resolved()
            else:
                stake = None
            premium = insurance_terms(balance, stake)[0] if insure and stake is not None else 0
            if premium and player.tokens < stake + premium:
                raise MetaError(f"Insurance costs {premium} chips on top of the stake")
            with db:
                if stake is not None:
                    db.execute("UPDATE player SET tokens = tokens - ?, lifetime_spend = lifetime_spend + ? "
                               "WHERE id = ?", (stake + premium, premium, player_id))
                for upgrade_id in bring:
                    db.execute("UPDATE player_upgrade SET amount = amount - 1 WHERE player_id = ? AND upgrade_id = ?",
                               (player_id, upgrade_id))
                db.execute("DELETE FROM player_upgrade WHERE player_id = ? AND amount <= 0", (player_id,))
                run_id = int(db.execute(
                    "INSERT INTO run_history (player_id, mode, balance_profile, balance_hash, seed, upgrades, stake, "
                    "insurance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (player_id, mode.id, config.balance_profile, config.balance_hash, seed, json.dumps(applied), stake,
                     premium),
                ).lastrowid)
                db.execute("UPDATE player SET last_played_at = datetime('now') WHERE id = ?", (player_id,))
        controller = GameController(config, loop_factory=loop_factory,
                                    save_fn=partial(save_run, conn=self._conn, player_id=player_id, run_id=run_id))
        self._trackers[run_id] = RunTracker(controller)
        self._log(run_id, controller)
        return RunStart(run_id, mode.id, config, applied, controller, notes)

    def track(self, run_id: int, controller: GameController) -> None:
        """Follow a run's controller again (e.g. after loading its save)."""
        old = self._trackers.pop(run_id, None)
        if old is not None:
            old.detach()
        self._trackers[run_id] = RunTracker(controller)
        self._log(run_id, controller)

    def _log(self, run_id: int, controller: GameController) -> None:
        """Write the run's table notices to data/table_logs/ (only for runs kept in a database file)."""
        self._unlog(run_id)
        path = db_path()
        if self._conn is not None or path == MEMORY:
            return
        self._logs[run_id] = TableLog(controller, Path(path).parent / "table_logs" / f"run-{run_id}.jsonl")

    def _unlog(self, run_id: int) -> None:
        log = self._logs.pop(run_id, None)
        if log is not None:
            log.detach()

    def pending_run(self, player_id: int) -> PendingRun | None:
        """Summary of the run `resume_run` would load, without loading or tracking it."""
        with self._db() as db:
            row = db.execute(
                "SELECT h.id, h.mode, json_extract(s.data, '$.round') AS round, "
                "json_extract(s.data, '$.money') AS money, s.updated_at FROM run_history h "
                "JOIN run_save s ON s.run_id = h.id WHERE h.player_id = ? AND h.result IS NULL "
                "ORDER BY s.updated_at DESC LIMIT 1", (player_id,),
            ).fetchone()
        if row is None:
            return None
        return PendingRun(int(row["id"]), row["mode"], int(row["round"] or 0), int(row["money"] or 0),
                          row["updated_at"])

    def resume_run(self, player_id: int, *, loop_factory: LoopFactory | None = None) -> RunStart | None:
        """The player's unfinished run that has a save, loaded and tracked; None if there is none."""
        with self._db() as db:
            row = db.execute(
                "SELECT h.id, h.mode, h.upgrades, s.name FROM run_history h JOIN run_save s ON s.run_id = h.id "
                "WHERE h.player_id = ? AND h.result IS NULL ORDER BY s.updated_at DESC LIMIT 1", (player_id,),
            ).fetchone()
            if row is None:
                return None
            try:
                data = load_run(row["name"], conn=db)
            except SaveNotFound:
                return None
        run_id = int(row["id"])
        controller = GameController.from_save(
            data, loop_factory=loop_factory,
            save_fn=partial(save_run, conn=self._conn, player_id=player_id, run_id=run_id),
        )
        self.track(run_id, controller)
        return RunStart(run_id, row["mode"], controller.config, json.loads(row["upgrades"] or "{}"), controller)

    def finish_run(self, run_id: int, controller: GameController) -> RunReward:
        """Pay tokens for a run that is over and record it."""
        if controller.run_end is None or controller.run_end.kind not in ("victory", "defeat"):
            raise MetaError("The run is not over yet")
        tracker = self._trackers.pop(run_id, None) or RunTracker(controller)
        self._unlog(run_id)
        summary = tracker.summary()
        tracker.detach()
        with self._db() as db:
            run = db.execute("SELECT * FROM run_history WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                raise MetaError(f"Unknown run {run_id}")
            if run["result"] is not None:
                raise MetaError("This run has already been settled")
            balance = self._balance(db, run["balance_profile"], fallback=True)
            player_id = run["player_id"]
            summary["after_relief"] = int(self._player(db, player_id).relief_streak > 0)  # Back from Broke
            with db:
                backfilled = unlocks.backfill(db, player_id, balance)  # earlier runs first, without this one
            result = controller.run_end.kind
            breakdown = [x for x in reward_tokens(balance, result, summary["rounds"], controller.run.start_money,
                                                  summary["peak_money"], chaos=controller.config.enable_chaos) if x[1]]
            back = 0
            if run["stake"] is not None:  # the vault: a win brings the cash home, a defeat pays what it owes
                if result == "victory":
                    back = controller.run.money
                    breakdown.insert(0, ("Brought home", back))
                else:
                    owed = _debt(controller)
                    vault = self._player(db, player_id).tokens
                    if owed and vault:
                        back = -min(owed, vault)
                        breakdown.append(("Debt paid", back))
                    if run["insurance"] and summary["rounds"] <= balance.meta_insurance_rounds:
                        breakdown.append(("Insurance payout", insurance_terms(balance, run["stake"])[1]))
            tokens = sum(t for _, t in breakdown)
            with db:
                db.execute(
                    "UPDATE run_history SET ended_at = datetime('now'), result = ?, rounds = ?, final_money = ?, "
                    "peak_money = ?, tokens_earned = ?, summary = ?, chips_back = ? WHERE id = ?",
                    (result, summary["rounds"], controller.run.money, summary["peak_money"], tokens,
                     json.dumps(summary), back, run_id),
                )
                db.execute("UPDATE player SET tokens = MAX(0, tokens + ?), lifetime_spend = lifetime_spend + ?, "
                           "last_played_at = datetime('now') WHERE id = ?",
                           (tokens, int(summary.get("spent", 0)), player_id))
                if result == "victory":
                    db.execute("UPDATE player SET relief_streak = 0 WHERE id = ?", (player_id,))
                db.execute("DELETE FROM run_save WHERE run_id = ?", (run_id,))
                self._record_seen(db, player_id, run["mode"], summary)
                facts = unlocks.facts(db.execute("SELECT * FROM run_history WHERE id = ?", (run_id,)).fetchone(),
                                      summary)
                unlocks.fold_run(db, player_id, facts)
                unlocked = backfilled + unlocks.evaluate(db, player_id, balance, facts, run_id)
                top = _stake_range(balance, run["mode"])
                reached = onboarding.after_run(db, player_id, run["mode"], result, run["stake"],
                                               top[1] if top else None)
            breakdown += [(f"Achievement: {u.name}", u.tokens) for u in unlocked if u.tokens]
            tokens += sum(u.tokens for u in unlocked)
            with db:
                relief = self._relief(db, player_id, balance) if result != "victory" else 0
            if relief:
                breakdown.append(("Relief from Poker Head", relief))
                tokens += relief
                with db:
                    if onboarding.reach(db, player_id, onboarding.FIRST_RELIEF):
                        reached.append(onboarding.FIRST_RELIEF)
            return RunReward(tokens, tuple(breakdown), result, self._player(db, player_id), tuple(unlocked),
                             tuple(reached))

    def abandon_run(self, run_id: int) -> None:
        """Give up a run: recorded as abandoned, no tokens (consumables stay used)."""
        tracker = self._trackers.pop(run_id, None)
        spent = tracker.spent if tracker is not None else 0
        if tracker is not None:
            tracker.detach()
        self._unlog(run_id)
        with self._db() as db, db:
            run = db.execute("SELECT player_id, balance_profile FROM run_history WHERE id = ? AND result IS NULL",
                             (run_id,)).fetchone()
            db.execute("UPDATE run_history SET ended_at = datetime('now'), result = 'abandoned', tokens_earned = 0, "
                       "chips_back = 0 WHERE id = ? AND result IS NULL", (run_id,))
            db.execute("DELETE FROM run_save WHERE run_id = ?", (run_id,))
            if run is not None:  # the stake stays on the table; Poker Head may still help
                db.execute("UPDATE player SET lifetime_spend = lifetime_spend + ? WHERE id = ?",
                           (spent, run["player_id"]))
                self._relief(db, run["player_id"], self._balance(db, run["balance_profile"], fallback=True))

    def history(self, player_id: int, limit: int = 50) -> list[RunRecord]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM run_history WHERE player_id = ? ORDER BY id DESC LIMIT ?",
                              (player_id, limit)).fetchall()
        return [RunRecord(
            r["id"], r["started_at"], r["ended_at"], r["mode"], r["result"], r["rounds"], r["final_money"],
            r["peak_money"], r["tokens_earned"], r["balance_profile"],
            json.loads(r["upgrades"] or "{}"), json.loads(r["summary"] or "{}"),
        ) for r in rows]

    def codex_seen(self, player_id: int) -> dict[tuple[str, str], int]:
        """{(kind, entry_id): times} the player has met each codex entry."""
        with self._db() as db:
            return {(r["kind"], r["entry_id"]): r["times"]
                    for r in db.execute("SELECT kind, entry_id, times FROM codex_seen WHERE player_id = ?",
                                        (player_id,))}

    # -------------------------------------------------------------- cosmetics

    def wardrobe(self, player_id: int, slot: str | None = None, profile: str | None = None) -> list[CosmeticOffer]:
        """Every cosmetic (of one slot) and its state for the player; hidden ones only once owned."""
        if slot is not None and slot not in COSMETIC_SLOTS:
            raise MetaError(f"Unknown cosmetic slot {slot!r}")
        with self._db() as db:
            player = self._player(db, player_id)
            balance = self._balance(db, profile)
            owned = unlocks.owned_cosmetics(db, player_id)
            all_owned = self._all_looks(db, profile)
            equipped = {c.id for c in unlocks.loadout(db, player_id, all_owned=all_owned).values()}
        prices = {p.cosmetic_id: tiers.shop_price(balance, player.lifetime_spend, p.cost)
                  for p in balance.cosmetic_prices}
        rewarded_by: dict[str, list[str]] = {}
        for r in balance.achievement_rewards:
            a = get_achievement(r.achievement_id)
            for cosmetic_id in r.cosmetic_ids if a is not None else ():
                rewarded_by.setdefault(cosmetic_id, []).append("???" if a.hidden else a.name)
        offers = []
        for c in cosmetics(slot):
            have = c.default or all_owned or c.id in owned
            if c.hidden and not have:
                continue
            price = None if c.default else prices.get(c.id)
            hints = [f"{price} chips"] if price is not None else []
            hints += [f"Achievement: {name}" for name in rewarded_by.get(c.id, ())]
            if have:
                reason = "Owned" if c.default or c.id in owned else "Unlocked"
            elif price is None:
                reason = "Not for sale"
            elif player.tokens < price:
                reason = f"Needs {price} chips"
            else:
                reason = ""
            hint = "Starter look" if c.default else " or ".join(hints) or "Not available yet"
            offers.append(CosmeticOffer(c, have, c.id in equipped, price, not reason, reason, hint))
        return offers

    def loadout(self, player_id: int) -> dict[str, str]:
        """Slot -> equipped cosmetic id; every slot is filled (defaults included)."""
        with self._db() as db:
            self._player(db, player_id)
            return {slot: c.id for slot, c in unlocks.loadout(db, player_id, all_owned=self._all_looks(db)).items()}

    def asset_aliases(self, player_id: int) -> dict[str, str]:
        """Base asset id -> asset id of the player's equipped looks, for the GUI's AssetManager."""
        with self._db() as db:
            self._player(db, player_id)
            return unlocks.asset_aliases(unlocks.loadout(db, player_id, all_owned=self._all_looks(db)))

    def equip(self, player_id: int, cosmetic_id: str) -> dict[str, str]:
        """Equip an owned cosmetic in its slot; returns the new loadout."""
        c = get_cosmetic(cosmetic_id)
        if c is None:
            raise MetaError(f"Unknown cosmetic {cosmetic_id!r}")
        with self._db() as db:
            self._player(db, player_id)
            if not unlocks.owns(db, player_id, c, all_owned=self._all_looks(db)):
                raise MetaError(f"You do not own {c.name} yet")
            with db:
                db.execute(
                    "INSERT INTO player_loadout (player_id, slot, cosmetic_id) VALUES (?, ?, ?) "
                    "ON CONFLICT(player_id, slot) DO UPDATE SET cosmetic_id = excluded.cosmetic_id",
                    (player_id, c.slot, c.id),
                )
            return {slot: e.id for slot, e in unlocks.loadout(db, player_id, all_owned=self._all_looks(db)).items()}

    def buy_cosmetic(self, player_id: int, cosmetic_id: str, profile: str | None = None) -> Player:
        c = get_cosmetic(cosmetic_id)
        if c is None:
            raise MetaError(f"Unknown cosmetic {cosmetic_id!r}")
        with self._db() as db:
            player = self._player(db, player_id)
            if unlocks.owns(db, player_id, c, all_owned=self._all_looks(db, profile)):
                raise MetaError(f"You already own {c.name}")
            balance = self._balance(db, profile)
            price = next((p.cost for p in balance.cosmetic_prices if p.cosmetic_id == c.id), None)
            if price is not None:
                price = tiers.shop_price(balance, player.lifetime_spend, price)
            if price is None:
                raise MetaError(f"{c.name} is not for sale")
            if player.tokens < price:
                raise MetaError(f"Needs {price} chips")
            with db:
                db.execute("UPDATE player SET tokens = tokens - ?, lifetime_spend = lifetime_spend + ? WHERE id = ?",
                           (price, price, player_id))
                unlocks.add_cosmetic(db, player_id, c.id, "shop")
            return self._player(db, player_id)

    def grant_cosmetic(self, player_id: int, cosmetic_id: str) -> bool:
        """Development / testing helper; False when the player already owns it."""
        if get_cosmetic(cosmetic_id) is None:
            raise MetaError(f"Unknown cosmetic {cosmetic_id!r}")
        with self._db() as db:
            self._player(db, player_id)
            with db:
                return unlocks.add_cosmetic(db, player_id, cosmetic_id, "grant")

    # ----------------------------------------------------------- achievements

    def achievements(self, player_id: int, profile: str | None = None) -> list[AchievementState]:
        """Every achievement with its progress. A player from before stats existed
        is backfilled from run history first (which may unlock and pay)."""
        with self._db() as db:
            self._player(db, player_id)
            balance = self._balance(db, profile)
            with db:
                unlocks.backfill(db, player_id, balance)
            ctx = unlocks.context(db, player_id)
            done = unlocks.unlocked(db, player_id)
        rewards = {r.achievement_id: r for r in balance.achievement_rewards}
        out = []
        for a in achievements_catalog():
            progress, goal = a.progress(ctx)
            r = rewards.get(a.id)
            out.append(AchievementState(a, a.id in done, done.get(a.id), goal if a.id in done else progress, goal,
                                        r.tokens if r else 0, r.cosmetic_ids if r else ()))
        return out

    def player_stats(self, player_id: int, *, best: bool = False) -> dict[str, int]:
        """Lifetime stat totals, or with `best` each stat's best single run
        (chaos_blackjack.achievements.stats)."""
        with self._db() as db:
            self._player(db, player_id)
            with db:
                unlocks.backfill(db, player_id, self._balance(db, None, fallback=True))
            return unlocks.stat_values(db, player_id)[1 if best else 0]

    # -------------------------------------------------------------- internals

    def _player(self, db: sqlite3.Connection, player_id: int) -> Player:
        row = db.execute("SELECT * FROM player WHERE id = ?", (player_id,)).fetchone()
        if row is None:
            raise MetaError(f"Unknown player {player_id}")
        upgrades = {r["upgrade_id"]: r["amount"] for r in db.execute(
            "SELECT upgrade_id, amount FROM player_upgrade WHERE player_id = ? AND amount > 0", (player_id,))}
        s = db.execute(
            "SELECT COUNT(*) AS runs, "
            "SUM(result = 'victory') AS v, SUM(result = 'defeat') AS d, SUM(result = 'abandoned') AS a, "
            "MAX(peak_money) AS best, SUM(tokens_earned) AS t FROM run_history "
            "WHERE player_id = ? AND result IS NOT NULL", (player_id,),
        ).fetchone()
        stats = PlayerStats(s["runs"] or 0, s["v"] or 0, s["d"] or 0, s["a"] or 0, s["best"] or 0, s["t"] or 0)
        avatar = unlocks.loadout(db, player_id, all_owned=self._all_looks(db))["avatar"].asset_map()["avatar"]
        return Player(row["id"], row["slot"], row["name"], row["tokens"], upgrades, stats,
                      row["created_at"], row["last_played_at"], avatar, row["relief_streak"], row["lifetime_spend"],
                      bool(row["guided"]))

    @classmethod
    def _all_looks(cls, db: sqlite3.Connection, profile: str | None = None) -> bool:
        """The profile's meta.unlock_all_cosmetics: every look counts as owned."""
        return cls._balance(db, profile, fallback=True).meta_unlock_all_cosmetics

    @staticmethod
    def _balance(db: sqlite3.Connection, profile: str | None, *, fallback: bool = False) -> Balance:
        try:
            return load_balance(profile, db)
        except BalanceError:
            if fallback:
                return default_balance()
            raise

    @staticmethod
    def _record_seen(db: sqlite3.Connection, player_id: int, mode: str, summary: dict[str, Any]) -> None:
        seen: list[tuple[str, str, int]] = [("mode", mode, 1)]
        seen += [("rule", r, n) for r, n in summary["rules_seen"].items()]
        items = dict(summary["items_bought"])
        for item, n in summary["items_used"].items():
            items[item] = items.get(item, 0) + n
        seen += [("item", i, n) for i, n in items.items()]
        if summary.get("chaos_ai"):
            seen.append(("ai", summary["chaos_ai"], 1))
        for kind, entry_id, n in seen:
            db.execute(
                "INSERT INTO codex_seen (player_id, kind, entry_id, times) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(player_id, kind, entry_id) DO UPDATE SET times = times + excluded.times",
                (player_id, kind, entry_id, n),
            )


def insurance_terms(balance: Balance, stake: int) -> tuple[int, int]:
    """(premium, refund) of early-bust insurance for a stake: the premium rounds up, the refund down."""
    premium = math.ceil(stake * balance.meta_insurance_premium_pct / 100)
    return premium, stake * balance.meta_insurance_refund_pct // 100


def _stake_range(balance: Balance, mode_id: str) -> tuple[int, int] | None:
    """`mode.<id>.stake` ("min,max") of a profile; None = the mode takes no stake."""
    raw = dict(balance.mode_settings).get(f"{mode_id}.stake")
    if not raw:
        return None
    lo, hi = (int(x) for x in str(raw).split(","))
    return lo, hi


def _debt(controller: GameController) -> int:
    """What a finished run still owes (a fourfold loss beyond the cash, open loans); 0 at tables without it."""
    ledger = getattr(controller.table, "ledger", None)
    return int(ledger.debt) if ledger is not None else 0


def _clean_name(name: str) -> str:
    clean = " ".join(name.split())
    if not clean:
        raise MetaError("Name cannot be empty")
    if len(clean) > MAX_NAME_LENGTH:
        raise MetaError(f"Name can be at most {MAX_NAME_LENGTH} characters")
    return clean
