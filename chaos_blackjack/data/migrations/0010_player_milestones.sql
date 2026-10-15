-- 0010: player onboarding (docs/design/TUTORIAL.md).
--   * player.guided: 1 = the player follows the onboarding (tutorial, table unlocks, first-time explanations);
--     every player from before this migration is 0 and counts as having seen all of it
--   * player_milestone: onboarding steps a guided player has reached

ALTER TABLE player ADD COLUMN guided INTEGER NOT NULL DEFAULT 0;

CREATE TABLE player_milestone (
    player_id   INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    milestone   TEXT    NOT NULL,
    reached_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_id, milestone)
);
