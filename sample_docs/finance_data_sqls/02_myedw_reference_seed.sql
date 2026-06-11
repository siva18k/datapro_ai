--\echo 'WARNING: This will TRUNCATE reference tables in schema myedw!'
--\echo 'To proceed, run: \set confirm_truncate on'
--\if :{?confirm_truncate}
--  \echo 'Confirmed. Proceeding with truncate and seed...'
  TRUNCATE TABLE
    myedw.reference_countries,
    myedw.reference_currencies,
    myedw.reference_departments,
    myedw.reference_job_titles,
    myedw.reference_employee_status,
    myedw.reference_sales_channels,
    myedw.reference_payment_methods,
    myedw.reference_document_types,
    myedw.reference_support_ticket_status,
    myedw.reference_calendar
  RESTART IDENTITY CASCADE;
--\else
--  \echo 'Seed aborted. Set confirm_truncate first if you want to overwrite data.'
--  \quit
--\endif

-- ===============================================================
-- 1. REFERENCE COUNTRIES
-- ===============================================================
INSERT INTO myedw.reference_countries(country_code, country_name)
VALUES
  ('US','United States'),
  ('CA','Canada'),
  ('GB','United Kingdom'),
  ('DE','Germany'),
  ('FR','France'),
  ('IN','India'),
  ('JP','Japan'),
  ('CN','China'),
  ('AU','Australia'),
  ('BR','Brazil')
ON CONFLICT (country_code) DO NOTHING;

-- ===============================================================
-- 2. REFERENCE CURRENCIES
-- ===============================================================
INSERT INTO myedw.reference_currencies(currency_code, currency_name, symbol)
VALUES
  ('USD','US Dollar','$'),
  ('CAD','Canadian Dollar','C$'),
  ('GBP','British Pound','£'),
  ('EUR','Euro','€'),
  ('INR','Indian Rupee','₹'),
  ('JPY','Japanese Yen','¥'),
  ('CNY','Chinese Yuan','¥'),
  ('AUD','Australian Dollar','A$'),
  ('BRL','Brazilian Real','R$')
ON CONFLICT (currency_code) DO NOTHING;


-- ===============================================================
-- 02_MYEDW_REFERENCE_SEED.SQL  (Segment 2 of 4)
-- Purpose : Populate HR, Sales, Document, and Support reference tables
-- ===============================================================

SET search_path TO myedw, public;

-- ===============================================================
-- 3. REFERENCE DEPARTMENTS
-- ===============================================================
INSERT INTO myedw.reference_departments(department_name)
VALUES
  ('Human Resources'),
  ('Finance'),
  ('Sales'),
  ('Marketing'),
  ('Support'),
  ('IT'),
  ('Operations'),
  ('Legal')
ON CONFLICT (department_name) DO NOTHING;

-- ===============================================================
-- 4. REFERENCE JOB TITLES
-- ===============================================================
INSERT INTO myedw.reference_job_titles(title_name)
VALUES
  ('Software Engineer'),
  ('Data Engineer'),
  ('Data Analyst'),
  ('HR Manager'),
  ('Finance Analyst'),
  ('Support Specialist'),
  ('Sales Executive'),
  ('Marketing Coordinator'),
  ('Operations Manager')
ON CONFLICT (title_name) DO NOTHING;

-- ===============================================================
-- 5. REFERENCE EMPLOYEE STATUS
-- ===============================================================
INSERT INTO myedw.reference_employee_status(status_code, description)
VALUES
  ('ACTIVE', 'Active Employee'),
  ('LEAVE', 'On Leave'),
  ('TERMINATED', 'Terminated'),
  ('RETIRED', 'Retired')
ON CONFLICT (status_code) DO NOTHING;

-- ===============================================================
-- 6. REFERENCE SALES CHANNELS
-- ===============================================================
INSERT INTO myedw.reference_sales_channels(channel_name, description)
VALUES
  ('Online', 'E-commerce and website sales'),
  ('Retail', 'Physical store transactions'),
  ('Partner', 'Reseller or distributor sales'),
  ('Direct', 'B2B or direct-to-customer')
ON CONFLICT (channel_name) DO NOTHING;

-- ===============================================================
-- 7. REFERENCE PAYMENT METHODS
-- ===============================================================
INSERT INTO myedw.reference_payment_methods(method_name, description)
VALUES
  ('Credit Card', 'Online or physical card payments'),
  ('Bank Transfer', 'Electronic bank-to-bank payments'),
  ('Cash', 'Cash transactions'),
  ('PayPal', 'Third-party online payment system'),
  ('Crypto', 'Blockchain-based payments')
ON CONFLICT (method_name) DO NOTHING;

-- ===============================================================
-- 8. REFERENCE DOCUMENT TYPES
-- ===============================================================
INSERT INTO myedw.reference_document_types(doc_type, description)
VALUES
  ('POLICY', 'HR or company policy document'),
  ('INVOICE', 'Financial invoice document'),
  ('REPORT', 'Operational or analytics report'),
  ('MANUAL', 'Technical or training manual'),
  ('CONTRACT', 'Vendor or employee contract')
ON CONFLICT (doc_type) DO NOTHING;

-- ===============================================================
-- 9. REFERENCE SUPPORT TICKET STATUS
-- ===============================================================
INSERT INTO myedw.reference_support_ticket_status(status_code, status_label)
VALUES
  ('OPEN', 'Ticket is open'),
  ('IN_PROGRESS', 'Assigned and being worked on'),
  ('RESOLVED', 'Issue resolved'),
  ('CLOSED', 'Ticket closed after verification')
ON CONFLICT (status_code) DO NOTHING;

-- ===============================================================
-- 02_MYEDW_REFERENCE_SEED.SQL  (Segment 3 of 4 - FIXED)
-- Purpose : Generate reference_calendar for 2023–2026
-- Matches columns: date_id, year, quarter, month, day, week, is_weekend, is_holiday
-- ===============================================================

SET search_path TO myedw, public;

DO $$
DECLARE
    start_date DATE := '2023-01-01';
    end_date   DATE := '2026-12-31';
    d DATE;
    dow INT;
    is_weekend BOOLEAN;
    qtr INT;
    is_holiday BOOLEAN;
BEGIN
    FOR d IN SELECT generate_series(start_date, end_date, interval '1 day')::date LOOP
        dow := EXTRACT(DOW FROM d);
        is_weekend := (dow IN (0,6));
        qtr := CASE
                 WHEN EXTRACT(MONTH FROM d) BETWEEN 1 AND 3 THEN 1
                 WHEN EXTRACT(MONTH FROM d) BETWEEN 4 AND 6 THEN 2
                 WHEN EXTRACT(MONTH FROM d) BETWEEN 7 AND 9 THEN 3
                 ELSE 4
               END;
        -- simple holiday set (extend later as needed)
        is_holiday := TO_CHAR(d,'MM-DD') IN ('01-01','07-04','11-11','12-25','12-31');

        INSERT INTO myedw.reference_calendar (
            date_id, "year", "quarter", "month", "day", "week", is_weekend, is_holiday
        )
        VALUES (
            d,
            EXTRACT(YEAR FROM d)::INT,
            qtr,
            EXTRACT(MONTH FROM d)::INT,
            EXTRACT(DAY FROM d)::INT,
            EXTRACT(WEEK FROM d)::INT,
            is_weekend,
            is_holiday
        )
        ON CONFLICT (date_id) DO NOTHING;
    END LOOP;
END $$;

-- quick sanity
SELECT MIN(date_id) AS min_date, MAX(date_id) AS max_date, COUNT(*) AS rows
FROM myedw.reference_calendar;

SELECT * FROM myedw.reference_calendar ORDER BY date_id LIMIT 5;


