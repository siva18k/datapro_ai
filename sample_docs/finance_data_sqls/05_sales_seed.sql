-- ===============================================================
-- 04_MYEDW_SALES_SEED.SQL
-- Complete Sales → Invoices → Payments → Shipments → Returns
-- ===============================================================

SET search_path TO myedw, public;

-- ===============================================================
-- 1️⃣ SALES ORDERS
-- ===============================================================
INSERT INTO myedw.sales_orders (order_id, customer_id, channel_id, order_date, status, total_amount, currency_code, payment_method_id)
WITH 
    vars AS (
        SELECT 
            (SELECT array_agg(customer_id) FROM myedw.customer_profiles) as cust_ids,
            (SELECT array_agg(channel_id) FROM myedw.reference_sales_channels) as chan_ids,
            (SELECT array_agg(payment_method_id) FROM myedw.reference_payment_methods) as pay_ids
    )
SELECT
    g AS order_id,
    cust_ids[floor(random() * array_length(cust_ids, 1)) + 1],
    chan_ids[floor(random() * array_length(chan_ids, 1)) + 1],
    DATE '2023-01-01' + (random() * 1000)::int,
    (ARRAY['PENDING','SHIPPED','RETURNED','CANCELLED'])[floor(random() * 4) + 1],
    round((50 + random() * 1500)::numeric, 2),
    'USD',
    pay_ids[floor(random() * array_length(pay_ids, 1)) + 1]
FROM generate_series(1, 5000) AS g
CROSS JOIN vars;

-- ===============================================================
-- 2️⃣ SALES ORDER ITEMS (1–5 per order)
-- ===============================================================
INSERT INTO myedw.sales_order_items (order_id, product_id, quantity, unit_price, discount_amount)
SELECT
    o.order_id,
    p.product_id,
    p.final_qty,
    p.unit_price,
    p.item_discount
FROM myedw.sales_orders o
CROSS JOIN LATERAL (
    SELECT 
        ip.product_id, 
        ip.unit_price,
        -- The addition of (o.order_id * 0) forces a fresh random per row
        (1 + floor(random() * 4 + (o.order_id * 0)))::int AS final_qty,
        round((ip.unit_price * (random() * 0.15))::numeric, 2) AS item_discount
    FROM myedw.inventory_products ip
    ORDER BY (random() + (o.order_id * 0)) 
    LIMIT (1 + floor(random() * 4))::int
) p
WHERE o.status IN ('PENDING','SHIPPED','RETURNED');
ON CONFLICT DO NOTHING;

-- ===============================================================
-- 1️⃣ UPDATE SALES ORDERS TO SYNC WITH SALES ORDER ITEMS TOTALS
-- ===============================================================
UPDATE myedw.sales_orders o
SET total_amount = sub.calculated_total
FROM (
    SELECT 
        order_id, 
        SUM(line_total) as calculated_total
    FROM myedw.sales_order_items
    GROUP BY order_id
) sub
WHERE o.order_id = sub.order_id;
-- ===============================================================
-- 3️⃣ SALES INVOICES (1 per order)
-- ===============================================================
INSERT INTO myedw.sales_invoices (order_id, invoice_date, due_date, total_amount, tax_amount, paid_amount, currency_code)
SELECT
    o.order_id,
    o.order_date + ((random() * 3)::int),
    o.order_date + ((random() * 15)::int),
    o.total_amount,
    round((o.total_amount * 0.07)::numeric, 2),
    CASE
        WHEN random() < 0.9 THEN round((o.total_amount * (0.9 + random() * 0.1))::numeric, 2)
        ELSE 0
    END,
    o.currency_code
FROM myedw.sales_orders o
WHERE NOT EXISTS (SELECT 1 FROM myedw.sales_invoices i WHERE i.order_id=o.order_id);

-- ===============================================================
-- 4️⃣ SALES PAYMENTS (~90% of invoices)
-- ===============================================================
INSERT INTO myedw.sales_payments (payment_id, invoice_id, payment_date, amount, method_id, reference_no)
SELECT
    nextval(pg_get_serial_sequence('myedw.sales_payments','payment_id')),
    i.invoice_id,
    i.invoice_date + ((random() * 10)::int),
    i.paid_amount,
    (SELECT payment_method_id FROM myedw.reference_payment_methods ORDER BY random() LIMIT 1),
    CONCAT('TXN-', (100000 + (random()*900000)::int))
FROM myedw.sales_invoices i
WHERE i.paid_amount > 0
  AND random() < 0.9
ON CONFLICT DO NOTHING;
-- ===============================================================
-- 5️⃣ SALES SHIPMENTS (~70% of SHIPPED orders)
-- ===============================================================
INSERT INTO myedw.sales_shipments (shipment_id, order_id, shipped_date, carrier, tracking_number, status)
SELECT
    nextval(pg_get_serial_sequence('myedw.sales_shipments','shipment_id')),
    o.order_id,
    o.order_date + ((random() * 7)::int),
    (ARRAY['FedEx','UPS','USPS','DHL','Amazon Logistics'])[1 + (random()*4)::int],
    CONCAT('TRK', (1000000 + (random()*9000000)::int)),
    (ARRAY['IN_TRANSIT','DELIVERED','RETURNED'])[1 + (random()*2)::int]
FROM myedw.sales_orders o
WHERE o.status='SHIPPED' AND random() < 0.8
ON CONFLICT DO NOTHING;

-- ===============================================================
-- 6️⃣ SALES RETURNS (~5% of shipped orders)
-- ===============================================================
-- ===============================================================
-- 5️⃣ SALES RETURNS (~5% of completed orders)
-- ===============================================================
INSERT INTO myedw.sales_returns (order_id, return_date, reason, refund_amount)
SELECT 
    o.order_id,
    o.order_date + ((random() * 30)::int),
    (ARRAY['Damaged','Not as described','Wrong item','Late delivery'])[1 + (random() * 3)::int],
    ROUND(
        (
            SELECT COALESCE(SUM((oi.quantity * oi.unit_price - oi.discount_amount)), 0)
            FROM myedw.sales_order_items oi 
            WHERE oi.order_id = o.order_id
        ) * (0.1 + random() * 0.5)
        ::numeric, 2
    )
FROM myedw.sales_orders o
WHERE o.status IN ('SHIPPED', 'RETURNED')
  AND random() < 0.05
  AND NOT EXISTS (SELECT 1 FROM myedw.sales_returns r WHERE r.order_id = o.order_id);


-- ===============================================================
-- ✅ SANITY CHECKS
-- ===============================================================
SELECT COUNT(*) AS total_orders FROM myedw.sales_orders;
SELECT COUNT(*) AS total_items FROM myedw.sales_order_items;
SELECT COUNT(*) AS total_invoices FROM myedw.sales_invoices;
SELECT COUNT(*) AS total_payments FROM myedw.sales_payments;
SELECT COUNT(*) AS total_shipments FROM myedw.sales_shipments;
SELECT COUNT(*) AS total_returns FROM myedw.sales_returns;

