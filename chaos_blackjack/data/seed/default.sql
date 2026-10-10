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
    (:profile, 'shop.refresh_rounds',     '2',            'int',  1,    NULL, 'Rounds between restocks');

-- Placeholder prices (not balanced yet).
INSERT INTO shop_item (profile_id, item_id, price_mode, price) VALUES
    (:profile, 'peek',             'fixed', 10),
    (:profile, 'danger_radar',     'fixed', 10),
    (:profile, 'swap',             'fixed', 20),
    (:profile, 'hole_card_hacker', 'fixed', 25),
    (:profile, 'fate_oracle',      'fixed', 25),
    (:profile, 'shield',           'fixed', 30);
