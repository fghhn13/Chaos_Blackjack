-- Add interaction settings to existing editable profiles without changing their tuning.
-- Fresh/default profiles get these values from seed/default.sql.
INSERT INTO setting (profile_id, key, value, type, min, max, description)
SELECT id, 'chaos.guidance_probability', '0.5', 'float', 0, 1,
       'Probability of guiding rather than misleading portrait advice'
FROM balance_profile AS p
WHERE NOT EXISTS (SELECT 1 FROM setting WHERE profile_id = p.id AND key = 'chaos.guidance_probability');

INSERT INTO setting (profile_id, key, value, type, min, max, description)
SELECT id, 'chaos.memory_enabled', '0', 'bool', NULL, NULL,
       'Collect and persist run-local Chaos history'
FROM balance_profile AS p
WHERE NOT EXISTS (SELECT 1 FROM setting WHERE profile_id = p.id AND key = 'chaos.memory_enabled');

INSERT INTO setting (profile_id, key, value, type, min, max, description)
SELECT id, 'chaos.memory_limit', '32', 'int', 1, NULL,
       'Maximum number of retained Chaos memory events'
FROM balance_profile AS p
WHERE NOT EXISTS (SELECT 1 FROM setting WHERE profile_id = p.id AND key = 'chaos.memory_limit');
