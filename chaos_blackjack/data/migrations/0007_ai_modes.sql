-- 0007: AI modes (docs/design/AI_MODES.md).
--   * meta upgrades may belong to one mode (NULL = every mode)
--   * the card_back cosmetic slot becomes deck (card back and face)
--   * an achievement may reward several cosmetics (comma-separated ids)

ALTER TABLE meta_upgrade ADD COLUMN mode TEXT;

UPDATE player_loadout SET slot = 'deck' WHERE slot = 'card_back';

ALTER TABLE achievement_reward RENAME COLUMN cosmetic_id TO cosmetic_ids;

-- Existing editable profiles: beating Poker Head (chaos_conqueror) now gives
-- the Poker Head deck and table; Chaos Velvet moves to the shop. Seeded
-- profiles are re-imported from their seed files right after migrating.
UPDATE achievement_reward SET cosmetic_ids = 'deck_poker_head,table_poker_head'
WHERE achievement_id = 'chaos_conqueror' AND cosmetic_ids = 'table_chaos';

INSERT INTO cosmetic_price (profile_id, cosmetic_id, cost)
SELECT p.id, 'table_chaos', 80 FROM balance_profile AS p
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_price WHERE profile_id = p.id AND cosmetic_id = 'table_chaos');
