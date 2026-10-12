-- The `default` balance profile: the game's shipped numbers.
--
-- This file is the single source of truth for default values. On start-up the
-- game re-imports it into the database whenever the file changes, so edit
-- here (and update black-jack-sim/bands.json when balance shifts on purpose).
-- To experiment, clone `default` into a new profile in the database instead.
-- `:profile` is the id of the `default` row, bound by the loader.

INSERT INTO setting (profile_id, key, value, type, min, max, description) VALUES
    (:profile, 'run.start_money',         '100',          'int',  2,    NULL, 'Bankroll at the start of a run'),
    (:profile, 'run.target_money',        '300',          'int',  3,    NULL, 'Bankroll that wins the run'),
    (:profile, 'run.objective',           'double_money', 'str',  NULL, NULL, 'Run objective id'),
    (:profile, 'table.dealer_stand_on',   '17',           'int',  2,    30,   'Dealer stands on this total or more'),
    (:profile, 'table.blackjack_pays_num','3',            'int',  1,    NULL, 'Natural blackjack payout numerator (3 in 3:2)'),
    (:profile, 'table.blackjack_pays_den','2',            'int',  1,    NULL, 'Natural blackjack payout denominator (2 in 3:2)'),
    (:profile, 'table.allow_double',      '1',            'bool', NULL, NULL, 'Double down allowed on the first decision'),
    (:profile, 'table.allow_surrender',   '1',            'bool', NULL, NULL, 'Surrender allowed on the first decision'),
    (:profile, 'shop.slots',              '3',            'int',  1,    NULL, 'Different items on sale per restock'),
    (:profile, 'shop.refresh_rounds',     '2',            'int',  1,    NULL, 'Rounds between restocks'),
    (:profile, 'shop.reroll_price',       '3',           'int',  0,    NULL, 'Chips for one reroll of the current stock (once per stock)'),
    (:profile, 'bet.min',                 '5',            'int',  1,    NULL, 'Smallest bet'),
    (:profile, 'bet.max_fraction',        '0.5',          'float',0.01, 1,    'Largest bet as a share of the bankroll (rounded down)'),
    (:profile, 'chaos.guidance_probability','0.5',        'float',0,    1,    'Probability of guiding rather than misleading portrait advice'),
    (:profile, 'chaos.memory_enabled',    '0',            'bool', NULL, NULL, 'Collect and persist run-local Chaos history'),
    (:profile, 'chaos.memory_limit',      '32',           'int',  1,    NULL, 'Maximum number of retained Chaos memory events'),
    (:profile, 'chaos.stub_calm_weight',  '15',           'float',0,    NULL, 'Offline Chaos AI weight for a calm round (no rule), next to each rule stub_weight'),
    (:profile, 'meta.win_tokens',         '10',           'int',  0,    NULL, 'Tokens for winning a run'),
    (:profile, 'meta.chaos_win_bonus',    '4',            'int',  0,    NULL, 'Extra tokens for winning a run with Chaos on'),
    (:profile, 'meta.bring_kinds',        '2',            'int',  0,    NULL, 'Different consumables a player may bring to one run'),
    (:profile, 'meta.loss_per_round',     '0.2',          'float',0,    NULL, 'Consolation tokens per round survived in a lost run'),
    (:profile, 'meta.loss_per_peak_gain', '4',            'float',0,    NULL, 'Consolation tokens per 100% of the start bankroll gained at the peak'),
    (:profile, 'meta.loss_cap',           '5',            'int',  0,    NULL, 'Most consolation tokens for a lost run');

-- Prices revised from agent playtest feedback. `params` is item tuning (JSON).
-- `bankroll_pct`: `price` is a percentage of the bankroll when the stock is
-- rolled, rounded half up with a minimum price of one chip.
INSERT INTO shop_item (profile_id, item_id, price_mode, price, params) VALUES
    (:profile, 'peek',             'bankroll_pct',  4, NULL),
    (:profile, 'danger_radar',     'bankroll_pct',  6, NULL),
    (:profile, 'swap',             'bankroll_pct', 2, NULL),
    (:profile, 'hole_card_hacker', 'bankroll_pct', 3, NULL),
    (:profile, 'fate_oracle',      'bankroll_pct', 8, '{"cards": 3}'),
    (:profile, 'shield',           'bankroll_pct', 5, NULL);

-- Sold only when the example content pack is loaded; unused plugin ids are
-- filtered by the run-scoped registry before the controller rolls stock.
INSERT INTO shop_item (profile_id, item_id, price_mode, price) VALUES
    (:profile, 'example_trim', 'fixed', 20);

-- Chaos rules. `params`: fixed tuning that wins over the AI's params.
-- `stub_weight` / `stub_params`: how often the offline Chaos AI (no LLM) picks
-- the rule and what it sends; `chaos.stub_calm_weight` is the weight of a calm
-- round. Player EV per round (black-jack-sim, basic strategy) is noted per rule;
-- the weighted mix is about -2 %, a little harder than plain blackjack.
INSERT INTO chaos_rule (profile_id, rule_id, enabled, params, stub_weight, stub_params) VALUES
    (:profile, 'modify_card_value', 1, NULL,                                  15, '{"delta": -1}'),        -- -10 %
    (:profile, 'reverse_bust',      1, NULL,                                   3, NULL),                   -- bust = push
    (:profile, 'great_crash',       1, '{"ten_value": 8}',                    10, NULL),                   -- -14 %
    (:profile, 'odd_even_chaos',    1, '{"even_delta": 2, "odd_delta": -1}',  22, NULL),                   --  +4 %
    (:profile, 'suit_power',        1, '{"red_delta": 1, "black_delta": -1}', 20, NULL),                   --  -5 %
    (:profile, 'fragile_bust',      1, '{"bust_limit": 19}',                  15, NULL),                   --  +8 %
    (:profile, 'tiebreaker_shift',  1, NULL,                                  15, '{"ties_to": "dealer"}'); --  -9 %

-- Meta upgrades bought with tokens between runs (tuned with black-jack-sim). Effects
-- are code (chaos_blackjack/meta/effects.py); each row is one upgrade.
-- Permanent: level n costs cost + (n - 1) * cost_step. Consumable: used up at
-- the start of the run it is brought to; max_level caps the copies held.
INSERT INTO meta_upgrade (profile_id, upgrade_id, kind, effect, params, cost, cost_step, max_level) VALUES
    (:profile, 'start_money',            'permanent',  'run.start_money_add', '{"amount": 10}',               20, 10, 3),
    (:profile, 'bag_space',              'permanent',  'meta.bring_kinds_add', '{"amount": 1}',               25, 15, 2),
    (:profile, 'reroll_pass',            'permanent',  'shop.free_rerolls_add', '{"amount": 1}',              30,  0, 1),
    (:profile, 'start_peek',             'consumable', 'run.starting_item',   '{"item": "peek"}',              4,  0, 3),
    (:profile, 'start_danger_radar',     'consumable', 'run.starting_item',   '{"item": "danger_radar"}',      3,  0, 3),
    (:profile, 'start_swap',             'consumable', 'run.starting_item',   '{"item": "swap"}',              6,  0, 3),
    (:profile, 'start_hole_card_hacker', 'consumable', 'run.starting_item',   '{"item": "hole_card_hacker"}',  8,  0, 3),
    (:profile, 'start_fate_oracle',      'consumable', 'run.starting_item',   '{"item": "fate_oracle"}',      15,  0, 3),
    (:profile, 'start_shield',           'consumable', 'run.starting_item',   '{"item": "shield"}',            8,  0, 3);

-- Cosmetics sold for tokens in the wardrobe (catalog: chaos_blackjack/cosmetics/catalog.py).
-- A cosmetic without a row is not sold. Placeholder prices.
INSERT INTO cosmetic_price (profile_id, cosmetic_id, cost) VALUES
    (:profile, 'card_back_crimson', 40),
    (:profile, 'table_midnight',    60),
    (:profile, 'chips_neon',        50),
    (:profile, 'avatar_spade',      30),
    (:profile, 'table_chaos',       80);

-- Achievement rewards (catalog: chaos_blackjack/achievements/catalog.py): tokens
-- and optional cosmetics (comma-separated ids). An achievement without a row
-- pays nothing. Placeholder values.
INSERT INTO achievement_reward (profile_id, achievement_id, tokens, cosmetic_ids) VALUES
    (:profile, 'first_win',           10, NULL),
    (:profile, 'chaos_conqueror',     10, 'deck_poker_head,table_poker_head'),
    (:profile, 'regular',              8, NULL),
    (:profile, 'marathon',            15, NULL),
    (:profile, 'natural_talent',       8, NULL),
    (:profile, 'blackjack_collector', 10, 'card_back_royal'),
    (:profile, 'double_trouble',      10, NULL),
    (:profile, 'five_card_trick',      8, NULL),
    (:profile, 'hot_streak',          10, NULL),
    (:profile, 'hundred_hands',       10, 'chips_gold'),
    (:profile, 'bare_hands',          12, NULL),
    (:profile, 'rule_scholar',        10, NULL),
    (:profile, 'white_flag',           5, 'avatar_joker');
