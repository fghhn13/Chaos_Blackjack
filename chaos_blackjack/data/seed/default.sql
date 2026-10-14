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
    (:profile, 'meta.win_tokens',         '0',            'int',  0,    NULL, 'Chips paid for winning a run on top of the cash brought home (off: the vault pays)'),
    (:profile, 'meta.chaos_win_bonus',    '0',            'int',  0,    NULL, 'Extra chips for winning a run with Chaos on (off)'),
    (:profile, 'meta.bring_kinds',        '2',            'int',  0,    NULL, 'Different consumables a player may bring to one run'),
    (:profile, 'meta.unlock_all_cosmetics', '0',          'int',  0,    1,    'Every player may wear every look (wardrobe and shop; nothing is stored)'),
    (:profile, 'meta.vault_start',        '1000',         'int',  0,    NULL, 'Chips in a new player''s vault'),
    (:profile, 'meta.relief_base',        '40',           'int',  0,    NULL, 'Poker Head''s first relief when the vault cannot cover Classic''s minimum stake'),
    (:profile, 'meta.relief_step',        '10',           'int',  0,    NULL, 'Relief added per earlier relief since the last won run'),
    (:profile, 'meta.relief_cap',         '100',          'int',  0,    NULL, 'Most relief at once'),
    (:profile, 'meta.insurance_premium_pct', '6',          'int',  0,    100,  'Early-bust insurance: premium, % of the stake'),
    (:profile, 'meta.insurance_refund_pct',  '50',         'int',  0,    100,  'Early-bust insurance: refund, % of the stake'),
    (:profile, 'meta.insurance_rounds',      '3',          'int',  1,    NULL, 'Early-bust insurance: a defeat within this many rounds pays'),
    (:profile, 'meta.membership_spend',      '0,1000,3000,8000,20000', 'str', NULL, NULL, 'Lifetime spend each membership level starts at'),
    (:profile, 'meta.membership_relief_bonus', '20',       'int',  0,    NULL, 'Relief cap added from membership level 3'),
    (:profile, 'meta.membership_shop_discount_pct', '5',   'int',  0,    100,  'Meta shop discount from membership level 4'),
    (:profile, 'meta.upgrades_enabled',   '0',            'int',  0,    1,    'Meta upgrades and starter items are sold and apply to runs (off in this version)'),
    (:profile, 'meta.loss_per_round',     '0.2',          'float',0,    NULL, 'Consolation tokens per round survived in a lost run'),
    (:profile, 'meta.loss_per_peak_gain', '4',            'float',0,    NULL, 'Consolation tokens per 100% of the start bankroll gained at the peak'),
    (:profile, 'meta.loss_cap',           '0',            'int',  0,    NULL, 'Most consolation chips for a lost run (off: Poker Head''s relief instead)');

-- Classic Table: goal and ceiling as a multiple of the starting cash (0 = run.target_money).
INSERT INTO setting (profile_id, key, value, type, min, max, description) VALUES
    (:profile, 'mode.normal.stake', '40,100', 'str', NULL, NULL, 'Chips a Classic run brings from the vault: min,max'),
    (:profile, 'mode.normal.config.target_multiple', '4', 'float', 0, NULL, 'Classic goal and ceiling as a multiple of the starting cash (0 = run.target_money)');

-- Poker Head builds: mode-scoped values; Classic and legacy chaos keep their numbers.
INSERT INTO setting (profile_id, key, value, type, min, max, description) VALUES
    (:profile, 'mode.chaos.build_version', '1', 'int', 0, 1, 'New Poker Head build version'),
    (:profile, 'mode.chaos.config.start_money', '400', 'int', 2, NULL, 'Cash at the start of a Poker Head run'),
    (:profile, 'mode.chaos.stake', '400,1000', 'str', NULL, NULL, 'Chips a Poker Head run brings from the vault: min,max'),
    (:profile, 'mode.chaos.money_base', '150', 'int', 1, NULL, 'Starting cash the Poker Head chip amounts are written for; they scale with the run''s starting cash'),
    (:profile, 'mode.chaos.config.target_money', '500', 'int', 1, NULL, 'Net assets needed to win at Poker Head'),
    (:profile, 'mode.chaos.config.target_multiple', '6', 'float', 0, NULL, 'Poker Head goal and ceiling as a multiple of the starting cash (0 = target_money)'),
    (:profile, 'mode.chaos.config.exit_multiple', '4', 'float', 0, NULL, 'Full Haul: net assets, as a multiple of the starting cash, from which the player may leave with a win (0 = never)'),
    (:profile, 'mode.chaos.config.objective', 'net_assets', 'str', NULL, NULL, 'Poker Head victory objective'),
    (:profile, 'mode.chaos.build_slots', '3', 'int', 1, NULL, 'Permanent build slots'),
    (:profile, 'mode.chaos.rule_slots', '3', 'int', 1, NULL, 'Persistent Chaos rule slots'),
    (:profile, 'mode.chaos.margin_bonus', '2', 'int', 0, NULL, 'Room to Breathe bust limit bonus'),
    (:profile, 'mode.chaos.approx_values', '20,22', 'str', NULL, NULL, 'Totals recognized as 21 after natural settlement'),
    (:profile, 'mode.chaos.surrender_pct', '20', 'int', 0, 100, 'Graceful Retreat loss percentage'),
    (:profile, 'mode.chaos.base_surrender_pct', '50', 'int', 0, 100, 'Undiscounted surrender fee percentage'),
    (:profile, 'mode.chaos.double_bonus_pct', '25', 'int', 0, NULL, 'High Stakes extra win percentage'),
    (:profile, 'mode.chaos.decline_cash', '30', 'int', 0, NULL, 'Extra starting chips for declining a core'),
    (:profile, 'mode.chaos.core_cash', '{"ph_margin":-60,"ph_late_retreat":60}', 'str', NULL, NULL, 'Chips a core costs (negative) or brings (positive) when chosen, JSON by core id'),
    (:profile, 'mode.chaos.extra_shop_slots', '1', 'int', 0, NULL, 'Private Account extra shop slots'),
    (:profile, 'mode.chaos.min_bets', '5,10,15,20,30,40', 'str', NULL, NULL, 'Minimum bet steps'),
    (:profile, 'mode.chaos.bet_step_rounds', '3', 'int', 1, NULL, 'Rounds per minimum bet step'),
    (:profile, 'mode.chaos.bet_step_add', '10', 'int', 0, NULL, 'Increase after the last minimum bet step'),
    (:profile, 'mode.chaos.reroll_step_add', '2', 'int', 0, NULL, 'Paid reroll price added per minimum bet step'),
    (:profile, 'mode.chaos.permanent_early', '0.2', 'float', 0, 1, 'Permanent offer probability in rounds 1 to 3'),
    (:profile, 'mode.chaos.permanent_middle', '0.3', 'float', 0, 1, 'Permanent offer probability in rounds 4 to 6'),
    (:profile, 'mode.chaos.permanent_late', '0.4', 'float', 0, 1, 'Permanent offer probability after round 6'),
    (:profile, 'mode.chaos.style_weight', '2', 'float', 0, NULL, 'Current core offer weight multiplier'),
    (:profile, 'mode.chaos.unlock_all', '0', 'int', 0, 1, 'Testing: every product on the shelf, money products without Private Account');

-- Poker Head's offline director (poker_head/director.py; design: POKER_HEAD_CHAOS_RULES_AND_AGENT.zh-CN.md §6).
INSERT INTO setting (profile_id, key, value, type, min, max, description) VALUES
    (:profile, 'mode.chaos.director.stages', '[[1,0.4,1,1],[5,0.6,2,3],[9,0.75,2,5],[13,0.85,3,6]]', 'str', NULL, NULL, 'Director stages: [first round, action chance, rule slots, pressure budget]'),
    (:profile, 'mode.chaos.director.weights', '{"shift":[45,35,25,20],"fixed":[35,20,15,10],"bust":[0,10,15,15],"tie":[0,10,10,10],"bust_outcome":[0,0,10,15],"profit_cap":[0,0,10,15],"item_ban":[0,5,5,5],"markup":[20,10,5,5],"hidden":[0,10,5,5]}', 'str', NULL, NULL, 'Director type weights per stage'),
    (:profile, 'mode.chaos.director.pools', '[{"fixed":{"single":2,"group":[8,9]},"shift":{"rank":[1,-1]},"markup":[[10,3]]},{"fixed":{"single":3,"group":[7,8]},"shift":{"rank":[1,-1],"group":[1,-1],"compound":[1]},"bust":[["player",20,2],["dealer",22,2]],"tie":["dealer"],"item_ban":[2],"markup":[[20,3]],"hidden":[2]},{"fixed":{"single":4,"group":[6,7,8]},"shift":{"rank":[1,-1,2,-2],"group":[1,-1,2,-2],"all":[1,-1]},"bust":[["player",19,2],["player",20,2],["dealer",22,2],["dealer",23,2]],"tie":["dealer"],"bust_outcome":[["dealer","push",2]],"profit_cap":[[50,3]],"item_ban":[2],"markup":[[30,3]],"hidden":[2]},{"fixed":{"single":4,"group":[5,6,7]},"shift":{"rank":[1,-1,2,-2],"group":[1,-1,2,-2],"all":[1,2,-1]},"bust":[["player",19,2],["player",20,2],["dealer",22,2],["dealer",23,2]],"tie":["dealer"],"bust_outcome":[["dealer","push",2]],"profit_cap":[[40,3],[30,3]],"item_ban":[3],"markup":[[40,3]],"hidden":[3]}]', 'str', NULL, NULL, 'Director variant pools per stage'),
    (:profile, 'mode.chaos.director.pressure', '{"fixed":1,"shift_local_1":1,"shift_local_2":2,"shift_compound":2,"shift_all":2,"bust":{"player:20":2,"player:19":3,"dealer:22":2,"dealer:23":3},"tie":2,"bust_outcome":3,"profit_cap":{"50":2,"40":3,"30":4},"item_ban":{"2":2,"3":3},"markup":{"10":1,"20":1,"30":2,"40":2},"hidden":2}', 'str', NULL, NULL, 'Director pressure per rule variant'),
    (:profile, 'mode.chaos.director.cooldown_cleared', '2', 'int', 0, NULL, 'Director actions a type waits after the player clears it'),
    (:profile, 'mode.chaos.director.cooldown_expired', '1', 'int', 0, NULL, 'Director actions a type waits after it ends'),
    (:profile, 'mode.chaos.director.cooldown_replaced', '2', 'int', 0, NULL, 'Director actions a replaced effect waits');

INSERT INTO shop_item (profile_id, item_id, price_mode, price, params) VALUES
    (:profile, 'ph_long_reward', 'fixed', 20, '{"bonus_pct":50,"cards":4}'),
    (:profile, 'ph_court', 'fixed', 40, '{"value":5}'),
    (:profile, 'ph_five_reward', 'fixed', 55, '{"bonus_pct":200,"cards":5}'),
    (:profile, 'ph_mark', 'fixed', 60, '{}'),
    (:profile, 'ph_retreat', 'fixed', 30, '{}'),
    (:profile, 'ph_loss_discount', 'fixed', 20, '{"discount_pct":10,"minimum_pct":10}'),
    (:profile, 'ph_claim', 'fixed', 40, '{}'),
    (:profile, 'ph_ace', 'fixed', 50, '{}'),
    (:profile, 'ph_jackpot', 'fixed', 80, '{"multiplier":3}'),
    (:profile, 'ph_sleeve', 'fixed', 35, '{}'),
    (:profile, 'ph_borrow', 'fixed', 55, '{}'),
    (:profile, 'ph_stakes', 'fixed', 25, '{}'),
    (:profile, 'ph_approx', 'fixed', 70, '{}'),
    (:profile, 'ph_risk', 'fixed', 40, '{"discount_pct":25}'),
    (:profile, 'ph_audit', 'fixed', 35, '{"threshold":10}'),
    (:profile, 'ph_discount', 'fixed', 15, '{"discount_pct":10}'),
    (:profile, 'ph_yield', 'fixed', 25, '{"bonus_pct":50}'),
    (:profile, 'ph_refresh', 'fixed', 15, '{}'),
    (:profile, 'ph_change', 'fixed', 20, '{}'),
    (:profile, 'ph_peek', 'fixed', 8, '{}'),
    (:profile, 'ph_swap', 'fixed', 10, '{}'),
    (:profile, 'ph_hole', 'fixed', 14, '{}'),
    (:profile, 'ph_radar', 'fixed', 6, '{}'),
    (:profile, 'ph_oracle', 'fixed', 16, '{}'),
    (:profile, 'ph_remove', 'fixed', 15, '{}'),
    (:profile, 'ph_silence', 'fixed', 10, '{}'),
    (:profile, 'ph_buffer', 'fixed', 5, '{"bonus":2}'),
    (:profile, 'ph_insurance', 'fixed', 12, '{}'),
    (:profile, 'ph_waiver', 'fixed', 10, '{}'),
    (:profile, 'ph_aces', 'fixed', 25, '{}'),
    (:profile, 'ph_undo', 'fixed', 12, '{}'),
    (:profile, 'ph_quad', 'fixed', 20, '{"multiplier":4}'),
    (:profile, 'ph_buyback', 'fixed', 6, '{}'),
    (:profile, 'ph_deposit', 'fixed', 30, '{"payout":50,"rounds":2}'),
    (:profile, 'ph_bond', 'fixed', 20, '{"failure":15,"payout":55,"rounds":3,"wins":2}'),
    (:profile, 'ph_stock', 'fixed', 30, '{"payout":100,"probability":0.5,"rounds":2}'),
    (:profile, 'ph_loan', 'fixed', 0, '{"advance":100,"repay":120,"rounds":3}');

-- J-54's table (demo, docs/design/J54_TABLE.md). First pass from a scripted bot:
-- a focused contract player wins ~17 % (capture) / ~11 % (capital), never
-- buying wins ~0 % / ~5 % and dies around round 18. Not balanced yet.
-- `mode.j54.config.<field>` overrides a RunConfig field at this table only.
INSERT INTO setting (profile_id, key, value, type, min, max, description) VALUES
    (:profile, 'mode.j54.protocols',        'capture,capital', 'str', NULL, NULL, 'Protocols (win conditions) a J-54 run draws from'),
    (:profile, 'mode.j54.capital_target',   '250',   'int', 1,    NULL, 'Capital protocol: bankroll that wins the run'),
    (:profile, 'mode.j54.experiment_jokers','1',     'int', 1,    NULL, 'Capture protocol: Jokers released by Start Experiment (all must be drawn)'),
    (:profile, 'mode.j54.fee_steps',        '0,1,2,4,8', 'str', NULL, NULL, 'Compute fee per round, one value per fee step; doubles after the last'),
    (:profile, 'mode.j54.fee_step_rounds',  '4',     'int', 1,    NULL, 'Rounds per compute fee step'),
    (:profile, 'mode.j54.entropy',          '1',     'int', 0,    NULL, 'Low cards J-54 adds to the deck after each round'),
    (:profile, 'mode.j54.entropy_experiment','2',    'int', 0,    NULL, 'Low cards J-54 adds after each round once the experiment started'),
    (:profile, 'mode.j54.dealer_joker_penalty','1',  'int', 0,    NULL, 'Low cards J-54 adds when it takes a Joker back from the dealer'),
    (:profile, 'mode.j54.min_deck',         '12',    'int', 8,    NULL, 'Deletions never shrink the deck below this many cards'),
    (:profile, 'mode.j54.config.shop_refresh_rounds', '1', 'int', 1, NULL, 'J-54 restocks its contracts every round');

-- Prices revised from agent playtest feedback. `params` is item tuning (JSON).
-- `bankroll_pct`: `price` is a percentage of the bankroll when the stock is
-- rolled, rounded half up with a minimum price of one chip.
INSERT INTO shop_item (profile_id, item_id, price_mode, price, params) VALUES
    (:profile, 'peek',             'bankroll_pct',  2, NULL),
    (:profile, 'danger_radar',     'bankroll_pct',  3, NULL),
    (:profile, 'swap',             'bankroll_pct', 1, NULL),
    (:profile, 'hole_card_hacker', 'bankroll_pct', 2, NULL),
    (:profile, 'fate_oracle',      'bankroll_pct', 4, '{"cards": 3}'),
    (:profile, 'shield',           'bankroll_pct', 3, NULL);

-- Sold only when the example content pack is loaded; unused plugin ids are
-- filtered by the run-scoped registry before the controller rolls stock.
INSERT INTO shop_item (profile_id, item_id, price_mode, price) VALUES
    (:profile, 'example_trim', 'fixed', 20);

-- J-54's run contracts (sold only at its table). `params`: a trigger (now, win,
-- loss, natural) and a deck operation (select / op / count, see
-- chaos_blackjack/j54/deck_ops.py) or a special effect (freeze, release_jokers).
INSERT INTO shop_item (profile_id, item_id, price_mode, price, params) VALUES
    (:profile, 'j54_streamline',        'fixed',  20, '{"trigger": "win", "select": "any", "op": "remove", "count": 5}'),
    (:profile, 'j54_low_purge',         'fixed',  10, '{"trigger": "now", "select": "low", "op": "remove", "count": 6}'),
    (:profile, 'j54_high_injection',    'fixed',  20, '{"trigger": "now", "select": "high", "op": "add", "count": 3}'),
    (:profile, 'j54_freeze',            'fixed',  15, '{"trigger": "now", "effect": "freeze", "rounds": 3}'),
    (:profile, 'j54_start_experiment',  'fixed',  50, '{"trigger": "now", "effect": "release_jokers"}');

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
    (:profile, 'tiebreaker_shift',  1, NULL,                                  15, '{"ties_to": "dealer"}'), --  -9 %
    -- J-54's deck rules (its table only): `params` is the deck operation
    -- (when / select / op / count, chaos_blackjack/j54/deck_ops.py). A new rule
    -- is a row here plus a name in rules/plugins/j54_deck.py.
    (:profile, 'j54_burn',              1, '{"when": "round_end", "select": "drawn", "op": "remove", "count": "all"}', 20, NULL),
    (:profile, 'j54_sample_injection',  1, '{"select": "random_rank", "op": "add", "count": 3}',      25, NULL),
    (:profile, 'j54_redundancy_purge',  1, '{"select": "random_rank", "op": "remove", "count": 3}',   25, NULL),
    (:profile, 'j54_ace_injection',     1, '{"select": "rank:A", "op": "add", "count": 1}',           10, NULL),
    (:profile, 'j54_layered_sort',      1, '{"select": "high", "op": "move_bottom", "count": "all"}', 10, NULL),
    (:profile, 'j54_data_backflow',     1, '{"select": "removed", "op": "return", "count": 4}',       10, NULL);

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
    (:profile, 'table_chaos',       80),
    -- J-54's look (assets/cosmetics/j54)
    (:profile, 'deck_j54',            60),
    (:profile, 'deck_j54_calculator', 60),
    (:profile, 'table_j54',           80),
    (:profile, 'chips_j54',           50),
    (:profile, 'avatar_j54',          30),
    (:profile, 'avatar_j54_computer', 30);

-- Achievement rewards (catalog: chaos_blackjack/achievements/catalog.py): tokens
-- and optional cosmetics (comma-separated ids). An achievement without a row
-- pays nothing. Placeholder values. Poker Face also hands out the rest of Poker
-- Head's House Collection until those looks get their own unlock rules.
INSERT INTO achievement_reward (profile_id, achievement_id, tokens, cosmetic_ids) VALUES
    (:profile, 'first_win',          100, NULL),
    (:profile, 'chaos_conqueror',    300, 'deck_poker_head,table_poker_head,deck_poker_head_gold,chips_poker_head,avatar_poker_head_j'),
    (:profile, 'regular',             80, NULL),
    (:profile, 'marathon',           150, NULL),
    (:profile, 'natural_talent',      80, NULL),
    (:profile, 'blackjack_collector',100, 'card_back_royal'),
    (:profile, 'double_trouble',     100, NULL),
    (:profile, 'five_card_trick',     80, NULL),
    (:profile, 'hot_streak',         100, NULL),
    (:profile, 'hundred_hands',      100, 'chips_gold'),
    (:profile, 'bare_hands',         120, NULL),
    (:profile, 'rule_scholar',       100, NULL),
    (:profile, 'white_flag',          50, 'avatar_joker'),
    (:profile, 'to_the_brim',        300, NULL),
    (:profile, 'in_and_out',         300, NULL),
    (:profile, 'all_in',             150, NULL),
    (:profile, 'saved_by_the_bell',  100, NULL),
    (:profile, 'fresh_start',        100, NULL),
    (:profile, 'back_from_broke',    500, NULL),
    (:profile, 'five_ways',          500, NULL);
