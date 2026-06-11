-- ===============================================================
-- 02_MYEDW_REFERENCE_SEED.SQL  (Segment 4 of 4 - FIXED)
-- Purpose : Sanity checks and referential integrity validation
-- ===============================================================

SET search_path TO myedw, public;

-- ===============================================================
-- 1️⃣ Row Counts for All Reference Tables
-- ===============================================================
SELECT table_name,
       (xpath('/row/cnt/text()', xml_count))[1]::text::int AS row_count
FROM (
  SELECT table_name,
         query_to_xml(format('SELECT COUNT(*) AS cnt FROM %I.%I', 'myedw', table_name), false, true, '') AS xml_count
  FROM information_schema.tables
  WHERE table_schema = 'myedw'
    AND table_name LIKE 'reference_%'
) AS t
ORDER BY table_name;

-- ===============================================================
-- 2️⃣ Calendar Summary
-- ===============================================================
SELECT MIN(date_id) AS min_date,
       MAX(date_id) AS max_date,
       COUNT(*)     AS total_days,
       SUM(CASE WHEN is_weekend THEN 1 ELSE 0 END) AS weekend_days,
       SUM(CASE WHEN is_holiday THEN 1 ELSE 0 END) AS holiday_days
FROM myedw.reference_calendar;

-- ===============================================================
-- 3️⃣ Country / Currency Link Check (No Bridge)
-- ===============================================================
SELECT c.country_code,
       c.country_name,
       c.currency_code,
       cur.currency_name
FROM myedw.reference_countries c
LEFT JOIN myedw.reference_currencies cur
       ON c.currency_code = cur.currency_code
LIMIT 10;

-- ===============================================================
-- 4️⃣ Department / Job Title / Employee Status Coverage
-- ===============================================================
SELECT
  (SELECT COUNT(*) FROM myedw.reference_departments)      AS departments,
  (SELECT COUNT(*) FROM myedw.reference_job_titles)       AS job_titles,
  (SELECT COUNT(*) FROM myedw.reference_employee_status)  AS emp_status;

-- ===============================================================
-- 5️⃣ Document & Support Metadata Health
-- ===============================================================
SELECT
  (SELECT COUNT(*) FROM myedw.reference_document_types)        AS doc_types,
  (SELECT COUNT(*) FROM myedw.reference_support_ticket_status) AS support_status,
  (SELECT COUNT(*) FROM myedw.reference_sales_channels)        AS sales_channels;

-- ===============================================================
-- 6️⃣ Quick Referential Sanity Across Key Dimensions
-- ===============================================================
SELECT
  (SELECT COUNT(*) FROM myedw.reference_calendar)        AS calendar_days,
  (SELECT COUNT(*) FROM myedw.reference_countries)       AS countries,
  (SELECT COUNT(*) FROM myedw.reference_currencies)      AS currencies,
  (SELECT COUNT(*) FROM myedw.reference_departments)     AS departments,
  (SELECT COUNT(*) FROM myedw.reference_sales_channels)  AS channels,
  (SELECT COUNT(*) FROM myedw.reference_payment_methods) AS payment_methods;

-- ===============================================================
-- ✅ End of Sanity Block
-- ===============================================================

