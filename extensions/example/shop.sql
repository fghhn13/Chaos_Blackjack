-- Install only into an editable balance profile that does not already carry it.
INSERT INTO shop_item (profile_id, item_id, price_mode, price) VALUES
    (:profile, 'example_trim', 'fixed', 20);
