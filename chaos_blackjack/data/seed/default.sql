-- The `default` balance profile: the game's shipped numbers.
--
-- This file is the single source of truth for default values. On start-up the
-- game re-imports it into the database whenever the file changes, so edit
-- here (and update black-jack-sim/bands.json when balance shifts on purpose).
-- To experiment, clone `default` into a new profile in the database instead.
-- `:profile` is the id of the `default` row, bound by the loader.

INSERT INTO setting (profile_id, key, value, type, min, max, description) VALUES
    (:profile, 'run.start_money',         '100',          'int',  2,    NULL, 'Bankroll at the start of a run'),
    (:profile, 'run.target_money',        '400',          'int',  3,    NULL, 'Bankroll that wins the run'),
    (:profile, 'run.objective',           'double_money', 'str',  NULL, NULL, 'Run objective id'),
    (:profile, 'table.dealer_stand_on',   '17',           'int',  2,    30,   'Dealer stands on this total or more'),
    (:profile, 'table.blackjack_pays_num','3',            'int',  1,    NULL, 'Natural blackjack payout numerator (3 in 3:2)'),
    (:profile, 'table.blackjack_pays_den','2',            'int',  1,    NULL, 'Natural blackjack payout denominator (2 in 3:2)'),
    (:profile, 'table.allow_double',      '1',            'bool', NULL, NULL, 'Double down allowed on the first decision'),
    (:profile, 'table.allow_surrender',   '1',            'bool', NULL, NULL, 'Surrender allowed on the first decision'),
    (:profile, 'shop.slots',              '3',            'int',  1,    NULL, 'Different items on sale per restock'),
    (:profile, 'shop.refresh_rounds',     '2',            'int',  1,    NULL, 'Rounds between restocks'),
    (:profile, 'bet.min',                 '1',            'int',  1,    NULL, 'Smallest bet'),
    (:profile, 'bet.max_fraction',        '0.5',          'float',0.01, 1,    'Largest bet as a share of the bankroll (rounded down)');

-- Placeholder prices (not balanced yet).
-- `params` is item tuning (JSON).
INSERT INTO shop_item (profile_id, item_id, price_mode, price, params) VALUES
    (:profile, 'peek',             'fixed', 10, NULL),
    (:profile, 'danger_radar',     'fixed', 10, NULL),
    (:profile, 'swap',             'fixed', 20, NULL),
    (:profile, 'hole_card_hacker', 'fixed', 25, NULL),
    (:profile, 'fate_oracle',      'fixed', 25, '{"cards": 3}'),
    (:profile, 'shield',           'fixed', 30, NULL);

-- Chaos rules. `params`: fixed tuning that wins over the AI's params.
-- `stub_weight` / `stub_params`: how often the offline Chaos AI (no LLM) picks
-- the rule and what it sends. Today it always applies "values -1".
INSERT INTO chaos_rule (profile_id, rule_id, enabled, params, stub_weight, stub_params) VALUES
    (:profile, 'modify_card_value', 1, NULL,                                  1, '{"delta": -1}'),
    (:profile, 'reverse_bust',      1, NULL,                                  0, NULL),
    (:profile, 'great_crash',       1, '{"ten_value": 1}',                    0, NULL),
    (:profile, 'odd_even_chaos',    1, '{"even_delta": 2, "odd_delta": -1}',  0, NULL),
    (:profile, 'suit_power',        1, '{"red_delta": 1, "black_delta": -1}', 0, NULL),
    (:profile, 'fragile_bust',      1, '{"bust_limit": 18}',                  0, NULL),
    (:profile, 'tiebreaker_shift',  1, NULL,                                  0, '{"ties_to": "dealer"}');
