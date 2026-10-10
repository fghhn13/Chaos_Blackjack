-- 0004: players (3 slots), their upgrades, run history, codex sightings, and
-- the meta upgrade catalog of each balance profile. See
-- docs/design/META_PROGRESSION.md.

CREATE TABLE player (
    id             INTEGER PRIMARY KEY,
    slot           INTEGER NOT NULL UNIQUE CHECK (slot BETWEEN 1 AND 3),
    name           TEXT    NOT NULL,
    tokens         INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    last_played_at TEXT
);

-- Permanent upgrades: amount = level. Consumables: amount = copies held.
CREATE TABLE player_upgrade (
    player_id  INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    upgrade_id TEXT    NOT NULL,
    amount     INTEGER NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (player_id, upgrade_id)
);

CREATE TABLE run_history (
    id              INTEGER PRIMARY KEY,
    player_id       INTEGER REFERENCES player(id) ON DELETE CASCADE,
    started_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT,
    mode            TEXT    NOT NULL,
    balance_profile TEXT,
    balance_hash    TEXT,
    seed            INTEGER,
    result          TEXT,                 -- victory | defeat | abandoned; NULL while running
    rounds          INTEGER,
    final_money     INTEGER,
    peak_money      INTEGER,
    tokens_earned   INTEGER,
    upgrades        TEXT,                 -- JSON {upgrade_id: level or copies used}
    summary         TEXT                  -- JSON run summary
);
CREATE INDEX run_history_player ON run_history (player_id, started_at);

CREATE TABLE codex_seen (
    player_id     INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    kind          TEXT    NOT NULL,
    entry_id      TEXT    NOT NULL,
    first_seen_at TEXT    NOT NULL DEFAULT (datetime('now')),
    times         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (player_id, kind, entry_id)
);

-- Catalog, per balance profile. Level n of a permanent upgrade costs
-- cost + (n - 1) * cost_step; for a consumable, max_level caps the copies held.
CREATE TABLE meta_upgrade (
    profile_id INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    upgrade_id TEXT    NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('permanent', 'consumable')),
    effect     TEXT    NOT NULL,
    params     TEXT,
    cost       INTEGER NOT NULL CHECK (cost >= 0),
    cost_step  INTEGER NOT NULL DEFAULT 0 CHECK (cost_step >= 0),
    max_level  INTEGER NOT NULL DEFAULT 1 CHECK (max_level >= 1),
    enabled    INTEGER NOT NULL DEFAULT 1,
    requires   TEXT,
    PRIMARY KEY (profile_id, upgrade_id)
);

ALTER TABLE run_save ADD COLUMN player_id INTEGER REFERENCES player(id) ON DELETE CASCADE;
ALTER TABLE run_save ADD COLUMN run_id INTEGER REFERENCES run_history(id) ON DELETE SET NULL;

-- Existing editable profiles get the new settings and the starting catalog
-- (snapshot of seed/default.sql at this version); seeded profiles are
-- re-imported from their seed files right after migrating.
INSERT INTO setting (profile_id, key, value, type, min, max, description)
SELECT p.id, s.key, s.value, s.type, s.min, s.max, s.description
FROM balance_profile AS p, (
    SELECT 'meta.win_tokens' AS key, '10' AS value, 'int' AS type, 0 AS min, NULL AS max,
           'Tokens for winning a run' AS description
    UNION ALL SELECT 'meta.loss_per_round', '0.2', 'float', 0, NULL,
           'Consolation tokens per round survived in a lost run'
    UNION ALL SELECT 'meta.loss_per_peak_gain', '4', 'float', 0, NULL,
           'Consolation tokens per 100% of the start bankroll gained at the peak'
    UNION ALL SELECT 'meta.loss_cap', '5', 'int', 0, NULL, 'Most consolation tokens for a lost run'
) AS s
WHERE NOT EXISTS (SELECT 1 FROM setting WHERE profile_id = p.id AND key = s.key);

INSERT INTO meta_upgrade (profile_id, upgrade_id, kind, effect, params, cost, cost_step, max_level)
SELECT p.id, u.upgrade_id, u.kind, u.effect, u.params, u.cost, u.cost_step, u.max_level
FROM balance_profile AS p, (
    SELECT 'start_money' AS upgrade_id, 'permanent' AS kind, 'run.start_money_add' AS effect,
           '{"amount": 10}' AS params, 15 AS cost, 10 AS cost_step, 3 AS max_level
    UNION ALL SELECT 'shop_slot', 'permanent', 'shop.slots_add', '{"amount": 1}', 40, 0, 1
    UNION ALL SELECT 'shop_discount', 'permanent', 'shop.discount_pct', '{"pct": 10}', 25, 15, 2
    UNION ALL SELECT 'start_peek', 'consumable', 'run.starting_item', '{"item": "peek"}', 5, 0, 9
    UNION ALL SELECT 'start_danger_radar', 'consumable', 'run.starting_item', '{"item": "danger_radar"}', 5, 0, 9
    UNION ALL SELECT 'start_swap', 'consumable', 'run.starting_item', '{"item": "swap"}', 10, 0, 9
    UNION ALL SELECT 'start_hole_card_hacker', 'consumable', 'run.starting_item', '{"item": "hole_card_hacker"}', 12, 0, 9
    UNION ALL SELECT 'start_fate_oracle', 'consumable', 'run.starting_item', '{"item": "fate_oracle"}', 12, 0, 9
    UNION ALL SELECT 'start_shield', 'consumable', 'run.starting_item', '{"item": "shield"}', 15, 0, 9
) AS u
WHERE NOT EXISTS (SELECT 1 FROM meta_upgrade WHERE profile_id = p.id);
