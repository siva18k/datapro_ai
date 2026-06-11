-- =====================================================================
-- 01_MYEDW_SCHEMA - CHUNK 4: VIEWS + SANITY BLOCK
-- Target: PostgreSQL 16.x
-- Schema: myedw
-- =====================================================================

SET search_path TO myedw, public;

-- =====================================================================
-- View: v_docs_by_department
-- =====================================================================
CREATE OR REPLACE VIEW myedw.v_docs_by_department AS
SELECT
    c.department,
    d.doc_type,
    COUNT(*) AS doc_count,
    SUM(d.size_bytes) AS total_size
FROM myedw.doc_documents d
JOIN myedw.doc_collections c ON c.collection_id = d.collection_id
GROUP BY c.department, d.doc_type
ORDER BY c.department, d.doc_type;
COMMENT ON VIEW myedw.v_docs_by_department IS 'Summary of documents by department and document type.';

-- =====================================================================
-- View: v_customer_order_summary
-- =====================================================================
CREATE OR REPLACE VIEW myedw.v_customer_order_summary AS
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(oi.line_total) AS total_revenue,
    MAX(o.order_date) AS last_order_date
FROM myedw.customer_profiles c
LEFT JOIN myedw.sales_orders o ON o.customer_id = c.customer_id
LEFT JOIN myedw.sales_order_items oi ON oi.order_id = o.order_id
GROUP BY c.customer_id, c.first_name, c.last_name;
COMMENT ON VIEW myedw.v_customer_order_summary IS 'Summarized view of each customer''s order history and revenue.';

-- =====================================================================
-- View: v_finance_summary
-- =====================================================================
CREATE OR REPLACE VIEW myedw.v_finance_summary AS
SELECT
    a.account_type,
    COUNT(DISTINCT j.journal_id) AS journals,
    SUM(l.debit_amount) AS total_debits,
    SUM(l.credit_amount) AS total_credits
FROM myedw.finance_journal_lines l
JOIN myedw.finance_accounts a ON a.account_id = l.account_id
JOIN myedw.finance_journal_entries j ON j.journal_id = l.journal_id
GROUP BY a.account_type;
COMMENT ON VIEW myedw.v_finance_summary IS 'Summarized debit/credit totals by account type.';

-- =====================================================================
-- View: v_support_ticket_status
-- =====================================================================
CREATE OR REPLACE VIEW myedw.v_support_ticket_status AS
SELECT
    a.agent_id,
    e.first_name || ' ' || e.last_name AS agent_name,
    t.status,
    COUNT(*) AS ticket_count
FROM myedw.support_tickets t
LEFT JOIN myedw.support_agents a ON a.agent_id = t.agent_id
LEFT JOIN myedw.hr_employees e ON e.employee_id = a.employee_id
GROUP BY a.agent_id, e.first_name, e.last_name, t.status;
COMMENT ON VIEW myedw.v_support_ticket_status IS 'Ticket counts per support agent by status.';

-- =====================================================================
-- View: v_hr_department_summary
-- =====================================================================
CREATE OR REPLACE VIEW myedw.v_hr_department_summary AS
SELECT
    d.department_name,
    COUNT(e.employee_id) AS employee_count,
    AVG(e.salary) AS avg_salary,
    SUM(e.salary) AS total_payroll
FROM myedw.hr_employees e
JOIN myedw.reference_departments d ON d.department_id = e.department_id
GROUP BY d.department_name;
COMMENT ON VIEW myedw.v_hr_department_summary IS 'Headcount and payroll summary by department.';

-- =====================================================================
-- View: v_finance_gl_summary
-- =====================================================================
CREATE OR REPLACE VIEW myedw.v_finance_gl_summary AS
SELECT
    a.account_code,
    a.account_name,
    a.account_type,
    SUM(l.debit_amount - l.credit_amount) AS balance
FROM myedw.finance_journal_lines l
JOIN myedw.finance_accounts a ON a.account_id = l.account_id
GROUP BY a.account_code, a.account_name, a.account_type;
COMMENT ON VIEW myedw.v_finance_gl_summary IS 'General ledger balances per account.';

-- =====================================================================
-- View: v_support_ticket_age
-- =====================================================================
CREATE OR REPLACE VIEW myedw.v_support_ticket_age AS
SELECT
    t.ticket_id,
    t.status,
    EXTRACT(DAY FROM (COALESCE(t.closed_at, CURRENT_TIMESTAMP) - t.opened_at))::INT AS ticket_age_days
FROM myedw.support_tickets t;
COMMENT ON VIEW myedw.v_support_ticket_age IS 'Age of each ticket in days based on open/close timestamps.';

-- =====================================================================
-- SANITY CHECKS: QUICK STRUCTURAL VALIDATION
-- =====================================================================

-- Row Counts per Key Table
SELECT 'customer_profiles' AS table_name, COUNT(*) FROM myedw.customer_profiles
UNION ALL SELECT 'sales_orders', COUNT(*) FROM myedw.sales_orders
UNION ALL SELECT 'sales_order_items', COUNT(*) FROM myedw.sales_order_items
UNION ALL SELECT 'sales_invoices', COUNT(*) FROM myedw.sales_invoices
UNION ALL SELECT 'finance_accounts', COUNT(*) FROM myedw.finance_accounts
UNION ALL SELECT 'hr_employees', COUNT(*) FROM myedw.hr_employees
UNION ALL SELECT 'support_tickets', COUNT(*) FROM myedw.support_tickets
UNION ALL SELECT 'doc_documents', COUNT(*) FROM myedw.doc_documents
ORDER BY table_name;

-- Aggregates for sanity verification
SELECT 
    'Total Revenue' AS metric, COALESCE(SUM(oi.line_total),0) AS value
FROM myedw.sales_order_items oi
UNION ALL
SELECT 'Total Employees', COUNT(*) FROM myedw.hr_employees
UNION ALL
SELECT 'Total Open Tickets', COUNT(*) FROM myedw.support_tickets WHERE status='OPEN'
UNION ALL
SELECT 'Total Documents', COUNT(*) FROM myedw.doc_documents;

