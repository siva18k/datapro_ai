-- Products for finance_data (matches 1_2 inventory_products DDL)
SET search_path TO finance_data, public;

TRUNCATE TABLE finance_data.inventory_products RESTART IDENTITY CASCADE;

INSERT INTO finance_data.inventory_products (product_code, product_name, category, unit_price, cost_price, currency_code, is_active)
SELECT
    'SKU' || LPAD(g::text, 6, '0'),
    'Product ' || g,
    (ARRAY['Electronics', 'Home & Kitchen', 'Books', 'Clothing', 'Sports', 'Health', 'Toys', 'Automotive'])[1 + (g % 8)],
    ROUND((15 + random() * 285)::numeric, 2),
    ROUND((8 + random() * 140)::numeric, 2),
    'USD',
    TRUE
FROM generate_series(1, 500) AS g;
