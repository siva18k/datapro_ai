-- ===============================================================
-- 05_MYEDW_FINANCE_SEED.SQL
-- Populates finance_ap_vendors, finance_accounts, finance_ap_bills,
-- finance_ap_bill_lines, finance_journal_entries, finance_journal_lines
-- ===============================================================

SET search_path TO myedw;

-- ===============================================================
-- 🧹 TRUNCATE ALL FINANCE TABLES
-- ===============================================================
DO $$
BEGIN
    EXECUTE 'TRUNCATE TABLE myedw.finance_journal_lines RESTART IDENTITY CASCADE';
    EXECUTE 'TRUNCATE TABLE myedw.finance_journal_entries RESTART IDENTITY CASCADE';
    EXECUTE 'TRUNCATE TABLE myedw.finance_ap_bill_lines RESTART IDENTITY CASCADE';
    EXECUTE 'TRUNCATE TABLE myedw.finance_ap_bills RESTART IDENTITY CASCADE';
    EXECUTE 'TRUNCATE TABLE myedw.finance_ap_vendors RESTART IDENTITY CASCADE';
    EXECUTE 'TRUNCATE TABLE myedw.finance_accounts RESTART IDENTITY CASCADE';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Finance tables truncated or empty.';
END$$;

-- ===============================================================
-- 🏢 ACCOUNTS CHART (General Ledger)
-- ===============================================================
INSERT INTO myedw.finance_accounts (account_code, account_name, account_type)
VALUES
 ('1000', 'Cash', 'ASSET'),
 ('1100', 'Accounts Receivable', 'ASSET'),
 ('1200', 'Inventory', 'ASSET'),
 ('1300', 'Prepaid Expenses', 'ASSET'),
 ('2000', 'Accounts Payable', 'LIABILITY'),
 ('2100', 'Accrued Liabilities', 'LIABILITY'),
 ('2200', 'Deferred Revenue', 'LIABILITY'),
 ('3000', 'Common Stock', 'EQUITY'),
 ('3100', 'Retained Earnings', 'EQUITY'),
 ('4000', 'Sales Revenue', 'REVENUE'),
 ('4100', 'Service Revenue', 'REVENUE'),
 ('5000', 'COGS', 'EXPENSE'),
 ('5100', 'Salaries Expense', 'EXPENSE'),
 ('5200', 'Rent Expense', 'EXPENSE'),
 ('5300', 'Utilities Expense', 'EXPENSE'),
 ('5400', 'Marketing Expense', 'EXPENSE'),
 ('5500', 'Depreciation Expense', 'EXPENSE'),
 ('5600', 'Office Supplies', 'EXPENSE'),
 ('6000', 'Income Tax Expense', 'EXPENSE');
-- ===============================================================
-- 🧑‍💼 VENDORS
-- ===============================================================
INSERT INTO myedw.finance_ap_vendors (vendor_code, vendor_name, country_code)
SELECT
    CONCAT('VEND-', LPAD(i::text, 4, '0')),
    (ARRAY[
        'Dell Technologies','Cisco Systems','Adobe','Oracle','Salesforce',
        'IBM','Infosys','Accenture','Amazon Web Services','Google Cloud',
        'HP Inc.','Apple Inc.','Sony','Lenovo','Intel','SAP','Zoom','Uber',
        'FedEx','UPS','Microsoft','Nvidia','Capgemini','Hitachi','TCS'
    ])[1 + (random()*23)::int],
    (ARRAY['US','CA','DE','IN','GB','JP','AU'])[1 + (random()*7)::int]
FROM generate_series(1,50) s(i);

INSERT INTO myedw.finance_ap_vendors (vendor_code, vendor_name, country_code) VALUES
('V100', 'Acme Supplies', 'US'),
('V200', 'TechSource Ltd', 'US'),
('V300', 'Global Stationers', 'US'),
('V400', 'Nova OfficeWorks', 'US'),
('V500', 'EcoPrint Solutions', 'US')
ON CONFLICT (vendor_code) DO NOTHING;


-- ===============================================================
-- 📑 ACCOUNTS PAYABLE BILLS
-- ===============================================================
INSERT INTO myedw.finance_ap_bills (vendor_id, bill_date, due_date, currency_code, status)
SELECT v.vendor_id,
       CURRENT_DATE - (v.vendor_id * INTERVAL '5 days'),
       CURRENT_DATE + (v.vendor_id * INTERVAL '3 days'),
       'USD',
       'OPEN'
FROM myedw.finance_ap_vendors v
ON CONFLICT DO NOTHING;
-- ===============================================================
-- 🧾 BILL LINES
-- ===============================================================
INSERT INTO myedw.finance_ap_bill_lines (bill_id, account_id, line_amount, description)
SELECT 
    b.bill_id,
    (SELECT account_id FROM myedw.finance_accounts ORDER BY RANDOM() LIMIT 1),
    ROUND((b.vendor_id * 500.00), 2),
    CONCAT('Expense line for Bill ID ', b.bill_id)
FROM myedw.finance_ap_bills b
ON CONFLICT DO NOTHING;
-- ===============================================================
-- 📘 JOURNAL ENTRIES
-- ===============================================================
-- =====================================================
--  Finance Domain Seed - Phase 5 (v3 - bigint clean)
--  Schema: myedw
--  Tables: finance_journal_entries, finance_journal_lines
--  Purpose: Balanced, deterministic, portable seed
-- =====================================================

-- Cleanup
TRUNCATE TABLE myedw.finance_journal_lines CASCADE;
TRUNCATE TABLE myedw.finance_journal_entries CASCADE;

-- =====================================================
-- Step 1: Seed journal entries
-- =====================================================
INSERT INTO myedw.finance_journal_entries (
    journal_id,
    entry_date,
    description,
    created_by
)
SELECT 
    seq AS journal_id,
    (DATE '2024-01-01' + (seq - 1))::date AS entry_date,
    CONCAT('Auto-generated journal entry #', seq) AS description,
    CASE WHEN seq % 2 = 0 THEN 1001 ELSE 1001 END AS created_by   -- numeric IDs
FROM generate_series(1, 20) AS seq;

-- =====================================================
-- Step 2: Create balanced journal lines
-- =====================================================
WITH acct AS (
    SELECT account_id, account_type, ROW_NUMBER() OVER (ORDER BY account_id) AS rn
    FROM myedw.finance_accounts
),
journals AS (
    SELECT journal_id, ROW_NUMBER() OVER (ORDER BY entry_date) AS rn
    FROM myedw.finance_journal_entries
)
INSERT INTO myedw.finance_journal_lines (
    line_id,
    journal_id,
    account_id,
    debit_amount,
    credit_amount
)
SELECT 
    (ROW_NUMBER() OVER ())::bigint AS line_id,
    j.journal_id,
    CASE WHEN j.rn % 2 = 0 THEN a1.account_id ELSE a2.account_id END AS account_id,
    CASE WHEN j.rn % 2 = 0 THEN 0 ELSE amt END AS debit_amount,
    CASE WHEN j.rn % 2 = 0 THEN amt ELSE 0 END AS credit_amount
FROM journals j
JOIN acct a1 ON a1.rn = ((j.rn - 1) % (SELECT COUNT(*) FROM acct)) + 1
JOIN acct a2 ON a2.rn = ((j.rn + 2) % (SELECT COUNT(*) FROM acct)) + 1
CROSS JOIN LATERAL (
    SELECT ROUND((1000 + (j.rn * 25))::numeric, 2) AS amt
) AS x;

-- =====================================================
-- Step 3: Validation – check journal balance
-- =====================================================
SELECT 
    je.journal_id,
    SUM(jl.debit_amount) AS total_debit,
    SUM(jl.credit_amount) AS total_credit,
    CASE 
        WHEN SUM(jl.debit_amount) = SUM(jl.credit_amount) THEN '✅ Balanced'
        ELSE '❌ Unbalanced'
    END AS status
FROM myedw.finance_journal_entries je
LEFT JOIN myedw.finance_journal_lines jl USING (journal_id)
GROUP BY je.journal_id
ORDER BY je.entry_date;

-- ===============================================================
-- ✅ SANITY CHECKS
-- ===============================================================
DO $$
DECLARE 
    diff NUMERIC;
BEGIN
    SELECT ROUND(SUM(debit_amount) - SUM(credit_amount),2)
    INTO diff
    FROM myedw.finance_journal_lines;
    IF diff <> 0 THEN
        RAISE NOTICE '⚠️ Journals are off by %', diff;
    ELSE
        RAISE NOTICE '✅ Journals balanced.';
    END IF;
END$$;

-- ===============================================================
-- END OF SCRIPT
-- ===============================================================

