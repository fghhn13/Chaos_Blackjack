-- 0006: cosmetics (owned and equipped per player), lifetime stats and
-- achievements, plus each balance profile's cosmetic prices and achievement
-- rewards. See docs/design/COSMETICS_ACHIEVEMENTS.md.

-- Owned cosmetics; each slot's default is owned implicitly and not stored.
CREATE TABLE player_cosmetic (
    player_id   INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    cosmetic_id TEXT    NOT NULL,
    source      TEXT    NOT NULL,          -- shop | achievement:<id> | grant
    acquired_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_id, cosmetic_id)
);

-- Equipped cosmetics; a slot without a row shows its default.
CREATE TABLE player_loadout (
    player_id   INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    slot        TEXT    NOT NULL,
    cosmetic_id TEXT    NOT NULL,
    PRIMARY KEY (player_id, slot)
);

-- Lifetime stats: total = sum over settled runs, best = highest single run.
CREATE TABLE player_stat (
    player_id INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    stat_id   TEXT    NOT NULL,
    total     INTEGER NOT NULL DEFAULT 0,
    best      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, stat_id)
);

-- A row = the achievement is unlocked.
CREATE TABLE player_achievement (
    player_id      INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    achievement_id TEXT    NOT NULL,
    unlocked_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    run_id         INTEGER REFERENCES run_history(id) ON DELETE SET NULL,
    PRIMARY KEY (player_id, achievement_id)
);

-- Catalog numbers, per balance profile. A cosmetic without a row is not sold;
-- an achievement without a row unlocks with no reward.
CREATE TABLE cosmetic_price (
    profile_id  INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    cosmetic_id TEXT    NOT NULL,
    cost        INTEGER NOT NULL CHECK (cost >= 0),
    enabled     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (profile_id, cosmetic_id)
);

CREATE TABLE achievement_reward (
    profile_id     INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    achievement_id TEXT    NOT NULL,
    tokens         INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    cosmetic_id    TEXT,
    PRIMARY KEY (profile_id, achievement_id)
);

-- Existing editable profiles get the starting prices and rewards (snapshot of
-- seed/default.sql at this version); seeded profiles are re-imported from
-- their seed files right after migrating.
INSERT INTO cosmetic_price (profile_id, cosmetic_id, cost)
SELECT p.id, c.cosmetic_id, c.cost
FROM balance_profile AS p, (
    SELECT 'card_back_crimson' AS cosmetic_id, 40 AS cost
    UNION ALL SELECT 'table_midnight', 60
    UNION ALL SELECT 'chips_neon', 50
    UNION ALL SELECT 'avatar_spade', 30
) AS c;

INSERT INTO achievement_reward (profile_id, achievement_id, tokens, cosmetic_id)
SELECT p.id, r.achievement_id, r.tokens, r.cosmetic_id
FROM balance_profile AS p, (
    SELECT 'first_win' AS achievement_id, 10 AS tokens, NULL AS cosmetic_id
    UNION ALL SELECT 'chaos_conqueror', 10, 'table_chaos'
    UNION ALL SELECT 'regular', 8, NULL
    UNION ALL SELECT 'marathon', 15, NULL
    UNION ALL SELECT 'natural_talent', 8, NULL
    UNION ALL SELECT 'blackjack_collector', 10, 'card_back_royal'
    UNION ALL SELECT 'double_trouble', 10, NULL
    UNION ALL SELECT 'five_card_trick', 8, NULL
    UNION ALL SELECT 'hot_streak', 10, NULL
    UNION ALL SELECT 'hundred_hands', 10, 'chips_gold'
    UNION ALL SELECT 'bare_hands', 12, NULL
    UNION ALL SELECT 'rule_scholar', 10, NULL
    UNION ALL SELECT 'white_flag', 5, 'avatar_joker'
) AS r;
