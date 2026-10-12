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
from dataclasses import dataclass
from functools import partial
from typing import Any

from chaos_blackjack.achievements import achievements_catalog, get_achievement
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.cosmetics import COSMETIC_SLOTS, cosmetics, get_cosmetic
from chaos_blackjack.data.balance import Balance, BalanceError, MetaUpgradeBalance, default_balance, load_balance
from chaos_blackjack.data.db import connect
from chaos_blackjack.data.saves import SaveNotFound, load_run, save_run
from chaos_blackjack.meta import unlocks
from chaos_blackjack.meta.effects import get_effect
from chaos_blackjack.meta.models import (
    MAX_NAME_LENGTH, SLOTS, AchievementState, CosmeticOffer, MetaError, PendingRun, Player, PlayerSlot, PlayerStats,
    RunRecord, RunReward, RunStart, UpgradeOffer,
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
    kinds = len(set(bring))
    if kinds > config.bring_kinds:
        raise MetaError(f"You can bring up to {config.bring_kinds} kinds of items (Bag Space raises this)")
    for upgrade_id in bring:
        u = catalog.get(upgrade_id)
        if u is None or u.kind != "consumable":
            raise MetaError(f"{upgrade_id!r} is not a consumable you can bring")
        if owned.get(upgrade_id, 0) < bring.count(upgrade_id):
            raise MetaError(f"You do not have enough {upgrade_id!r}")
        applied[upgrade_id] = applied.get(upgrade_id, 0) + 1
        config = _apply_upgrade(u, config, 1)
    return config, applied


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
            with db:
                backfilled = unlocks.backfill(db, player_id, balance)  # earlier runs first, without this one
            result = controller.run_end.kind
            breakdown = reward_tokens(balance, result, summary["rounds"], controller.run.start_money,
                                      summary["peak_money"], chaos=controller.config.enable_chaos)
            tokens = max(0, sum(t for _, t in breakdown))
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
                facts = unlocks.facts(db.execute("SELECT * FROM run_history WHERE id = ?", (run_id,)).fetchone(),
                                      summary)
                unlocks.fold_run(db, player_id, facts)
                unlocked = backfilled + unlocks.evaluate(db, player_id, balance, facts, run_id)
            breakdown += [(f"Achievement: {u.name}", u.tokens) for u in unlocked if u.tokens]
            tokens += sum(u.tokens for u in unlocked)
            return RunReward(tokens, tuple(breakdown), result, self._player(db, player_id), tuple(unlocked))

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

    # -------------------------------------------------------------- cosmetics

    def wardrobe(self, player_id: int, slot: str | None = None, profile: str | None = None) -> list[CosmeticOffer]:
        """Every cosmetic (of one slot) and its state for the player; hidden ones only once owned."""
        if slot is not None and slot not in COSMETIC_SLOTS:
            raise MetaError(f"Unknown cosmetic slot {slot!r}")
        with self._db() as db:
            player = self._player(db, player_id)
            balance = self._balance(db, profile)
            owned = unlocks.owned_cosmetics(db, player_id)
            equipped = {c.id for c in unlocks.loadout(db, player_id).values()}
        prices = {p.cosmetic_id: p.cost for p in balance.cosmetic_prices}
        rewarded_by: dict[str, list[str]] = {}
        for r in balance.achievement_rewards:
            a = get_achievement(r.achievement_id)
            if r.cosmetic_id and a is not None:
                rewarded_by.setdefault(r.cosmetic_id, []).append("???" if a.hidden else a.name)
        offers = []
        for c in cosmetics(slot):
            have = c.default or c.id in owned
            if c.hidden and not have:
                continue
            price = None if c.default else prices.get(c.id)
            hints = [f"{price} tokens"] if price is not None else []
            hints += [f"Achievement: {name}" for name in rewarded_by.get(c.id, ())]
            if have:
                reason = "Owned"
            elif price is None:
                reason = "Not for sale"
            elif player.tokens < price:
                reason = f"Needs {price} tokens"
            else:
                reason = ""
            hint = "Starter look" if c.default else " or ".join(hints) or "Not available yet"
            offers.append(CosmeticOffer(c, have, c.id in equipped, price, not reason, reason, hint))
        return offers

    def loadout(self, player_id: int) -> dict[str, str]:
        """Slot -> equipped cosmetic id; every slot is filled (defaults included)."""
        with self._db() as db:
            self._player(db, player_id)
            return {slot: c.id for slot, c in unlocks.loadout(db, player_id).items()}

    def asset_aliases(self, player_id: int) -> dict[str, str]:
        """Base asset id -> asset id of the player's equipped looks, for the GUI's AssetManager."""
        with self._db() as db:
            self._player(db, player_id)
            return unlocks.asset_aliases(unlocks.loadout(db, player_id))

    def equip(self, player_id: int, cosmetic_id: str) -> dict[str, str]:
        """Equip an owned cosmetic in its slot; returns the new loadout."""
        c = get_cosmetic(cosmetic_id)
        if c is None:
            raise MetaError(f"Unknown cosmetic {cosmetic_id!r}")
        with self._db() as db:
            self._player(db, player_id)
            if not unlocks.owns(db, player_id, c):
                raise MetaError(f"You do not own {c.name} yet")
            with db:
                db.execute(
                    "INSERT INTO player_loadout (player_id, slot, cosmetic_id) VALUES (?, ?, ?) "
                    "ON CONFLICT(player_id, slot) DO UPDATE SET cosmetic_id = excluded.cosmetic_id",
                    (player_id, c.slot, c.id),
                )
            return {slot: e.id for slot, e in unlocks.loadout(db, player_id).items()}

    def buy_cosmetic(self, player_id: int, cosmetic_id: str, profile: str | None = None) -> Player:
        c = get_cosmetic(cosmetic_id)
        if c is None:
            raise MetaError(f"Unknown cosmetic {cosmetic_id!r}")
        with self._db() as db:
            player = self._player(db, player_id)
            if unlocks.owns(db, player_id, c):
                raise MetaError(f"You already own {c.name}")
            price = next((p.cost for p in self._balance(db, profile).cosmetic_prices if p.cosmetic_id == c.id), None)
            if price is None:
                raise MetaError(f"{c.name} is not for sale")
            if player.tokens < price:
                raise MetaError(f"Needs {price} tokens")
            with db:
                db.execute("UPDATE player SET tokens = tokens - ? WHERE id = ?", (price, player_id))
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
                                        r.tokens if r else 0, r.cosmetic_id if r else None))
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
        avatar = unlocks.loadout(db, player_id)["avatar"].asset_map()["avatar"]
        return Player(row["id"], row["slot"], row["name"], row["tokens"], upgrades, stats,
                      row["created_at"], row["last_played_at"], avatar)

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
