-- Balance v1 settings: shop rerolls, calm offline Chaos rounds, the Chaos win
-- bonus and the consumable kinds a player may bring.
--
-- Existing editable profiles get the keys with values that keep their old
-- behaviour (no calm rounds, no bonus, any number of kinds), so they can be
-- edited with `python -m chaos_blackjack.data set`. Seeded profiles are
-- re-imported from their seed files right after migrating.
INSERT INTO setting (profile_id, key, value, type, min, max, description)
SELECT p.id, s.key, s.value, s.type, s.min, s.max, s.description
FROM balance_profile AS p, (
    SELECT 'shop.reroll_price' AS key, '10' AS value, 'int' AS type, 0 AS min, NULL AS max,
           'Chips for one reroll of the current stock (once per stock)' AS description
    UNION ALL SELECT 'chaos.stub_calm_weight', '0', 'float', 0, NULL,
           'Offline Chaos AI weight for a calm round (no rule), next to each rule stub_weight'
    UNION ALL SELECT 'meta.chaos_win_bonus', '0', 'int', 0, NULL, 'Extra tokens for winning a run with Chaos on'
    UNION ALL SELECT 'meta.bring_kinds', '99', 'int', 0, NULL, 'Different consumables a player may bring to one run'
) AS s
WHERE NOT EXISTS (SELECT 1 FROM setting WHERE profile_id = p.id AND key = s.key);
