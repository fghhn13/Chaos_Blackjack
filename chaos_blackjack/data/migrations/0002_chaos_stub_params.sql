-- 0002: AI params the offline Chaos AI sends with a rule (e.g. {"delta": -1}).
-- `chaos_rule.params` stays for fixed tuning that wins over any AI's params.

ALTER TABLE chaos_rule ADD COLUMN stub_params TEXT;
