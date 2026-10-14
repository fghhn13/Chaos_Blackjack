-- 0009: early-bust insurance bought with a staked run (docs/design/META_PROGRESSION.md "Chip vault").
--   run_history.insurance: the premium paid (0 = not insured)

ALTER TABLE run_history ADD COLUMN insurance INTEGER NOT NULL DEFAULT 0;
