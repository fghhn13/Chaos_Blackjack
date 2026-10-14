-- 0008: the chip vault (docs/design/META_PROGRESSION.md "Chip vault", CARRIED_CHIPS.zh-CN.md).
--   * player.tokens is now the chip vault; every existing player starts it at 1000 chips
--   * relief_streak: reliefs since the last won run; lifetime_spend: chips spent on goods
--   * run_history records the stake brought to the table and the chips brought home
--   * looks a player was wearing for free stay theirs when free looks end

ALTER TABLE player ADD COLUMN relief_streak INTEGER NOT NULL DEFAULT 0;
ALTER TABLE player ADD COLUMN lifetime_spend INTEGER NOT NULL DEFAULT 0;
ALTER TABLE run_history ADD COLUMN stake INTEGER;
ALTER TABLE run_history ADD COLUMN chips_back INTEGER;

UPDATE player SET tokens = 1000;

INSERT OR IGNORE INTO player_cosmetic (player_id, cosmetic_id, source)
SELECT player_id, cosmetic_id, 'grant' FROM player_loadout;
