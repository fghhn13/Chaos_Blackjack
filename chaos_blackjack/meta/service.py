"""MetaService — players, meta shop, runs and history on the game database.

Front-ends use the module-level functions in `chaos_blackjack.meta`, which
delegate to one service. Tests and GUI development can install a service on
an in-memory database (`chaos_blackjack.meta.fake`). Contract:
docs/design/META_PROGRESSION.md §5.1.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from typing import Any

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.data.balance import Balance, BalanceError, MetaUpgradeBalance, default_balance, load_balance
from chaos_blackjack.data.db import connect
from chaos_blackjack.data.saves import SaveNotFound, load_run, save_run
from chaos_blackjack.meta.effects import get_effect
from chaos_blackjack.meta.models import (
    MAX_NAME_LENGTH, SLOTS, MetaError, Player, PlayerSlot, PlayerStats, RunRecord, RunReward, RunStart,
    UpgradeOffer,
)
from chaos_blackjack.meta.tracker import RunTracker
from chaos_blackjack.modes import GameMode, get_mode, modes as all_modes

LoopFactory = Callable[[Any], Any]


@dataclass(frozen=True)
class ModeOption:
    mode: GameMode
    unlocked: bool


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
    `owned` holds levels / copies; owned upgrades the profile no longer sells
    are skipped. Raises MetaError for consumables that cannot be brought."""
    catalog = {u.upgrade_id: u for u in balance.meta_upgrades}
    config = mode.apply(RunConfig.from_balance(balance, seed=seed))
    applied: dict[str, int] = {}
    for upgrade_id, level in sorted(owned.items()):
        u = catalog.get(upgrade_id)
        if u is None or u.kind != "permanent" or level < 1:
            continue  # no longer sold in this profile, or a consumable
        applied[upgrade_id] = min(level, u.max_level)
        config = _apply_upgrade(u, config, applied[upgrade_id])
    bring = list(consumables)
    for upgrade_id in bring:
        u = catalog.get(upgrade_id)
        if u is None or u.kind != "consumable":
            raise MetaError(f"{upgrade_id!r} is not a consumable you can bring")
        if owned.get(upgrade_id, 0) < bring.count(upgrade_id):
            raise MetaError(f"You do not have enough {upgrade_id!r}")
        applied[upgrade_id] = applied.get(upgrade_id, 0) + 1
        config = _apply_upgrade(u, config, 1)
    return config, applied


def reward_tokens(balance: Balance, result: str, rounds: int, start: int, peak: int) -> list[tuple[str, int]]:
    """Token breakdown for a finished run: the win reward, or the consolation."""
    if result == "victory":
        return [("Victory", balance.meta_win_tokens)]
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
                with db:
                    pid = db.execute("INSERT INTO player (slot, name) VALUES (?, ?)", (slot, clean)).lastrowid
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
        """Development / testing helper: add (or remove) tokens."""
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
                                "Not available in this version")
        maxed = owned >= u.max_level
        cost = None if maxed else u.cost_of_level(owned + 1)
        if maxed:
            reason = "Maximum level" if u.kind == "permanent" else f"You can hold at most {u.max_level}"
        elif u.requires and player.upgrades.get(u.requires, 0) < 1:
            reason = f"Requires {u.requires}"
        elif cost is not None and player.tokens < cost:
            reason = f"Needs {cost} tokens"
        else:
            reason = ""
        return UpgradeOffer(u.upgrade_id, name, description, u.kind, owned, u.max_level, cost, not reason, reason)

    # ------------------------------------------------------------------- runs

    def modes(self, player_id: int | None = None) -> list[ModeOption]:
        upgrades = self.get_player(player_id).upgrades if player_id is not None else {}
        return [ModeOption(m, m.unlocked_by is None or upgrades.get(m.unlocked_by, 0) > 0) for m in all_modes()]

    def start_run(
        self,
        player_id: int,
        mode_id: str,
        *,
        consumables: Iterable[str] = (),
        profile: str | None = None,
        seed: int | None = None,
        loop_factory: LoopFactory | None = None,
    ) -> RunStart:
        """Build the run's config (profile + mode + upgrades), use up the chosen
        consumables, record the run and return a tracked controller."""
        try:
            mode = get_mode(mode_id)
        except KeyError as e:
            raise MetaError(str(e)) from None
        bring = list(consumables)
        with self._db() as db:
            player = self._player(db, player_id)
            if mode.unlocked_by and player.upgrades.get(mode.unlocked_by, 0) < 1:
                raise MetaError(f"The {mode.name} mode is locked")
            balance = self._balance(db, profile)
            config, applied = build_run_config(balance, mode, player.upgrades, bring, seed=seed)
            with db:
                for upgrade_id in bring:
                    db.execute("UPDATE player_upgrade SET amount = amount - 1 WHERE player_id = ? AND upgrade_id = ?",
                               (player_id, upgrade_id))
                db.execute("DELETE FROM player_upgrade WHERE player_id = ? AND amount <= 0", (player_id,))
                run_id = int(db.execute(
                    "INSERT INTO run_history (player_id, mode, balance_profile, balance_hash, seed, upgrades) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (player_id, mode.id, config.balance_profile, config.balance_hash, seed, json.dumps(applied)),
                ).lastrowid)
                db.execute("UPDATE player SET last_played_at = datetime('now') WHERE id = ?", (player_id,))
        controller = GameController(config, loop_factory=loop_factory,
                                    save_fn=partial(save_run, conn=self._conn, player_id=player_id, run_id=run_id))
        self._trackers[run_id] = RunTracker(controller)
        return RunStart(run_id, mode.id, config, applied, controller)

    def track(self, run_id: int, controller: GameController) -> None:
        """Follow a run's controller again (e.g. after loading its save)."""
        old = self._trackers.pop(run_id, None)
        if old is not None:
            old.detach()
        self._trackers[run_id] = RunTracker(controller)

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
        summary = tracker.summary()
        tracker.detach()
        with self._db() as db:
            run = db.execute("SELECT * FROM run_history WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                raise MetaError(f"Unknown run {run_id}")
            if run["result"] is not None:
                raise MetaError("This run has already been settled")
            balance = self._balance(db, run["balance_profile"], fallback=True)
            result = controller.run_end.kind
            breakdown = reward_tokens(balance, result, summary["rounds"], controller.run.start_money,
                                      summary["peak_money"])
            tokens = max(0, sum(t for _, t in breakdown))
            player_id = run["player_id"]
            with db:
                db.execute(
                    "UPDATE run_history SET ended_at = datetime('now'), result = ?, rounds = ?, final_money = ?, "
                    "peak_money = ?, tokens_earned = ?, summary = ? WHERE id = ?",
                    (result, summary["rounds"], controller.run.money, summary["peak_money"], tokens,
                     json.dumps(summary), run_id),
                )
                db.execute("UPDATE player SET tokens = tokens + ?, last_played_at = datetime('now') WHERE id = ?",
                           (tokens, player_id))
                db.execute("DELETE FROM run_save WHERE run_id = ?", (run_id,))
                self._record_seen(db, player_id, run["mode"], summary)
            return RunReward(tokens, tuple(breakdown), result, self._player(db, player_id))

    def abandon_run(self, run_id: int) -> None:
        """Give up a run: recorded as abandoned, no tokens (consumables stay used)."""
        tracker = self._trackers.pop(run_id, None)
        if tracker is not None:
            tracker.detach()
        with self._db() as db, db:
            db.execute("UPDATE run_history SET ended_at = datetime('now'), result = 'abandoned', tokens_earned = 0 "
                       "WHERE id = ? AND result IS NULL", (run_id,))
            db.execute("DELETE FROM run_save WHERE run_id = ?", (run_id,))

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
        return Player(row["id"], row["slot"], row["name"], row["tokens"], upgrades, stats,
                      row["created_at"], row["last_played_at"])

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


def _clean_name(name: str) -> str:
    clean = " ".join(name.split())
    if not clean:
        raise MetaError("Name cannot be empty")
    if len(clean) > MAX_NAME_LENGTH:
        raise MetaError(f"Name can be at most {MAX_NAME_LENGTH} characters")
    return clean
