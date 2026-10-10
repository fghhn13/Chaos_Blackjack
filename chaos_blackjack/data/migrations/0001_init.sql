-- 0001: balance profiles, settings, shop items, chaos rules, saves, preferences.
-- Never edit a migration that has shipped; add 0002_*.sql instead.

CREATE TABLE balance_profile (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    parent_id   INTEGER REFERENCES balance_profile(id) ON DELETE SET NULL,
    description TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    locked      INTEGER NOT NULL DEFAULT 0,   -- 1 = managed by seed/*.sql, do not edit
    source_hash TEXT                          -- hash of the seed file a locked profile came from
);

-- One tunable number (or flag / string) per row, e.g. 'run.start_money'.
CREATE TABLE setting (
    profile_id  INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    key         TEXT    NOT NULL,
    value       TEXT    NOT NULL,
    type        TEXT    NOT NULL CHECK (type IN ('int', 'float', 'bool', 'str')),
    min         REAL,
    max         REAL,
    description TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (profile_id, key)
);

CREATE TABLE shop_item (
    profile_id  INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    item_id     TEXT    NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    price_mode  TEXT    NOT NULL DEFAULT 'fixed' CHECK (price_mode IN ('fixed', 'bankroll_pct')),
    price       REAL    NOT NULL CHECK (price >= 0),
    weight      REAL    NOT NULL DEFAULT 1 CHECK (weight >= 0),
    params      TEXT,                          -- JSON object, item-specific
    PRIMARY KEY (profile_id, item_id)
);

CREATE TABLE chaos_rule (
    profile_id  INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    rule_id     TEXT    NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    params      TEXT,                          -- JSON object, rule-specific
    stub_weight REAL    NOT NULL DEFAULT 1 CHECK (stub_weight >= 0),
    PRIMARY KEY (profile_id, rule_id)
);

CREATE TABLE run_save (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    profile_name TEXT,
    balance_hash TEXT,
    save_version INTEGER NOT NULL,
    data         TEXT NOT NULL                 -- RunSaveData JSON
);

CREATE TABLE preference (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
