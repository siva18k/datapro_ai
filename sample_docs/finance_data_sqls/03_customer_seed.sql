-- ===============================================================
-- 03_MYEDW_CUSTOMER_SEED.SQL (FIXED)
-- Phase 3 - Segment 1: Customer Profiles, Accounts, Addresses, Loyalty, Preferences, Segments
-- ===============================================================

SET search_path TO myedw, public;

-- ===============================================================
-- 0️⃣ PREP - Optional cleanup for re-runs
-- ===============================================================
 TRUNCATE TABLE myedw.customer_segments_bridge CASCADE;
 TRUNCATE TABLE myedw.customer_preferences CASCADE;
 TRUNCATE TABLE myedw.customer_loyalty_points CASCADE;
 TRUNCATE TABLE myedw.customer_addresses CASCADE;
 TRUNCATE TABLE myedw.customer_accounts CASCADE;
 TRUNCATE TABLE myedw.customer_profiles CASCADE;

-- ===============================================================
-- 1️⃣ CUSTOMER PROFILES (≈250 records)
-- ===============================================================
INSERT INTO myedw.customer_profiles (customer_id, customer_code, first_name, last_name, email, phone, created_date, country_code)
SELECT
    g AS customer_id,
    CONCAT('CUST', LPAD(g::text, 5, '0')),
    (ARRAY['Alice','Bob','Carlos','Diana','Eva','Frank','Grace','Hiro','Ibrahim','Julia','Ken','Lara','Mona','Nina','Omar','Pia','Quinn','Ravi','Sara','Tom','Uma','Vik','Walt','Xiu','Yara','Zane'])[1 + (random()*25)::int],
    (ARRAY['Nguyen','Johnson','Diaz','Khan','Muller','Obrien','Lee','Tanaka','Singh','Garcia','Kim','Patel','Lopez','Rossi','Brown','Anders','Ivanov','Cohen','Zhou','Smith'])[1 + (random()*19)::int],
    LOWER(CONCAT('user', g, '@mypersonalspace.com')),
    CONCAT('+1-555-', LPAD((1000 + (random()*8999)::int)::text, 4, '0')),
    DATE '2023-01-01' + ((random()*700)::int),
    (SELECT country_code FROM myedw.reference_countries ORDER BY random() LIMIT 1)
FROM generate_series(1,250) AS g
--ON CONFLICT (customer_id) DO NOTHING;

-- ===============================================================
-- 2️⃣ CUSTOMER ACCOUNTS (1–2 per customer)
-- ===============================================================
INSERT INTO myedw.customer_accounts (account_id, customer_id, account_number, opened_date, status)
SELECT
    nextval(pg_get_serial_sequence('myedw.customer_accounts','account_id')),
    c.customer_id,
    CONCAT('ACCT-', LPAD(c.customer_id::text, 6, '0'), '-', (1 + (random()*2)::int)),
    c.created_date + ((random()*60)::int),
    (ARRAY['ACTIVE','SUSPENDED','CLOSED'])[1 + (random()*2)::int]
FROM myedw.customer_profiles c
CROSS JOIN generate_series(1,2) n
WHERE random() < 0.6
ON CONFLICT DO NOTHING;

-- ===============================================================
-- 3️⃣ CUSTOMER ADDRESSES (Primary + Secondary)
-- ===============================================================
INSERT INTO myedw.customer_addresses (address_id, customer_id, line1, line2, city, postal_code, country_code, is_primary)
SELECT
    nextval(pg_get_serial_sequence('myedw.customer_addresses','address_id')),
    c.customer_id,
    CONCAT((100 + (random()*900)::int), ' ', (ARRAY['Main St','Oak Ave','Pine Rd','Maple Dr','Elm St'])[1 + (random()*4)::int]),
    NULL,
    (ARRAY['New York','Los Angeles','Chicago','Houston','Phoenix','Dallas','Miami','Seattle','Boston','Denver'])[1 + (random()*9)::int],
    LPAD((10000 + (random()*89999)::int)::text,5,'0'),
    c.country_code,
    (random() < 0.7)
FROM myedw.customer_profiles c
CROSS JOIN generate_series(1,2) n
WHERE random() < 0.7
ON CONFLICT DO NOTHING;

-- ===============================================================
-- 4️⃣ CUSTOMER LOYALTY POINTS
-- ===============================================================
INSERT INTO myedw.customer_loyalty_points (customer_id, points_balance)
SELECT customer_id, (100 + (random()*5000)::int)
FROM myedw.customer_profiles
ON CONFLICT (customer_id) DO NOTHING;

-- ===============================================================
-- 5️⃣ CUSTOMER PREFERENCES
-- ===============================================================
INSERT INTO myedw.customer_preferences (pref_id, customer_id, prefers_email, prefers_sms)
SELECT
    nextval(pg_get_serial_sequence('myedw.customer_preferences','pref_id')),
    customer_id,
    (random() < 0.8),
    (random() < 0.4)
FROM myedw.customer_profiles
--ON CONFLICT (customer_id) DO NOTHING;

-- ===============================================================
-- 6️⃣ CUSTOMER SEGMENTS & BRIDGE
-- ===============================================================
INSERT INTO myedw.customer_segments (segment_id, segment_name, description)
SELECT s, segs[1], segs[2]
FROM (
  VALUES
    (1, ARRAY['VIP','High lifetime value']),
    (2, ARRAY['At Risk','Potential churn']),
    (3, ARRAY['New','First-time customers'])
) AS v(s,segs)
ON CONFLICT (segment_id) DO NOTHING;

INSERT INTO myedw.customer_segments_bridge (customer_id, segment_id, assigned_date)
SELECT
    c.customer_id,
    (ARRAY[1,2,3])[1 + (random()*2)::int],
    c.created_date + ((random()*90)::int)
FROM myedw.customer_profiles c
WHERE random() < 0.9
ON CONFLICT DO NOTHING;

-- ===============================================================
-- ✅ SANITY CHECKS
-- ===============================================================
SELECT COUNT(*) AS total_customers FROM myedw.customer_profiles;
SELECT COUNT(*) AS total_accounts FROM myedw.customer_accounts;
SELECT COUNT(*) AS total_addresses FROM myedw.customer_addresses;
SELECT COUNT(*) AS total_segments FROM myedw.customer_segments_bridge;
SELECT COUNT(*) AS total_prefs FROM myedw.customer_preferences;

-- ===============================================================
-- ✅ End of File
-- ===============================================================



