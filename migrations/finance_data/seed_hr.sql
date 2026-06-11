-- HR seed (fixed for finance_data / 1_3 FKs to reference_* tables)
SET search_path TO finance_data, public;

TRUNCATE TABLE finance_data.hr_performance_reviews RESTART IDENTITY CASCADE;
TRUNCATE TABLE finance_data.hr_payroll RESTART IDENTITY CASCADE;
TRUNCATE TABLE finance_data.hr_employees RESTART IDENTITY CASCADE;
TRUNCATE TABLE finance_data.hr_job_titles RESTART IDENTITY CASCADE;
TRUNCATE TABLE finance_data.hr_departments RESTART IDENTITY CASCADE;

INSERT INTO finance_data.hr_departments (department_id, department_name) VALUES
(10, 'Finance'),
(20, 'Human Resources'),
(30, 'Sales'),
(40, 'IT'),
(50, 'Operations'),
(60, 'Marketing');

INSERT INTO finance_data.hr_employees (
    employee_id, first_name, last_name,
    department_id, job_title_id,
    hire_date, salary, email, phone, status_code, country_code
) VALUES
(1001, 'John', 'Doe', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Finance' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Finance Analyst' LIMIT 1), '2020-01-10', 85000, 'john.doe@demo.com', '240-111-1212', 'ACTIVE', 'US'),
(1002, 'Mary', 'Smith', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Human Resources' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'HR Manager' LIMIT 1), '2019-07-15', 78000, 'mary.smith@demo.com', '240-111-1213', 'ACTIVE', 'US'),
(1003, 'Robert', 'Brown', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Sales' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Sales Executive' LIMIT 1), '2021-03-12', 90000, 'robert.brown@demo.com', '240-111-1214', 'ACTIVE', 'US'),
(1004, 'Linda', 'Garcia', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'IT' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Software Engineer' LIMIT 1), '2018-09-20', 95000, 'linda.garcia@demo.com', '240-111-1215', 'ACTIVE', 'US'),
(1005, 'James', 'Wilson', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Operations' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Operations Manager' LIMIT 1), '2022-02-14', 72000, 'james.wilson@demo.com', '240-111-1216', 'ACTIVE', 'US'),
(1006, 'Patricia', 'Miller', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Marketing' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Marketing Coordinator' LIMIT 1), '2020-11-30', 70000, 'patricia.miller@demo.com', '240-111-1217', 'ACTIVE', 'US'),
(1007, 'Michael', 'Taylor', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Finance' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Data Analyst' LIMIT 1), '2021-06-18', 68000, 'michael.taylor@demo.com', '240-111-1218', 'ACTIVE', 'US'),
(1008, 'Jennifer', 'Davis', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'IT' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Data Engineer' LIMIT 1), '2019-04-05', 98000, 'jennifer.davis@demo.com', '240-111-1219', 'ACTIVE', 'US'),
(1009, 'William', 'Anderson', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'IT' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Data Engineer' LIMIT 1), '2020-12-11', 94000, 'william.anderson@demo.com', '240-111-1220', 'ACTIVE', 'US'),
(1010, 'Susan', 'Thomas', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Sales' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Sales Executive' LIMIT 1), '2022-01-05', 62000, 'susan.thomas@demo.com', '240-111-1221', 'ACTIVE', 'US'),
(1011, 'Brian', 'Lane', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Sales' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Sales Executive' LIMIT 1), '2022-01-05', 62000, 'brian.lane@demo.com', '240-111-1222', 'LEAVE', 'US'),
(1012, 'Craig', 'Craig', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Sales' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Sales Executive' LIMIT 1), '2022-01-05', 62000, 'craig.craig@demo.com', '240-111-1223', 'TERMINATED', 'US'),
(1013, 'Moses', 'Johnson', (SELECT department_id FROM finance_data.reference_departments WHERE department_name = 'Sales' LIMIT 1), (SELECT job_title_id FROM finance_data.reference_job_titles WHERE title_name = 'Sales Executive' LIMIT 1), '2022-01-05', 62000, 'moses.johnson@demo.com', '240-111-1224', 'TERMINATED', 'US');

INSERT INTO finance_data.hr_payroll (payroll_id, employee_id, pay_period_start, pay_period_end, gross_pay, tax_withheld, net_pay)
SELECT
    (e.employee_id * 10 + p.seq) AS payroll_id,
    e.employee_id,
    DATE '2024-01-01' + (p.seq - 1) * 30 AS pay_period_start,
    DATE '2024-01-31' + (p.seq - 1) * 30 AS pay_period_end,
    ROUND((e.salary / 12)::numeric, 2) AS gross_pay,
    ROUND(((e.salary / 12) * 0.22)::numeric, 2) AS tax_withheld,
    ROUND(((e.salary / 12) * 0.78)::numeric, 2) AS net_pay
FROM finance_data.hr_employees e
CROSS JOIN generate_series(1, 3) AS p(seq);

INSERT INTO finance_data.hr_performance_reviews (review_id, employee_id, review_year, rating, reviewer_id, comments)
SELECT
    e.employee_id AS review_id,
    e.employee_id,
    2024,
    ROUND((3.5 + (random() * 1.0))::numeric, 1),
    1001,
    'Annual review seed data'
FROM finance_data.hr_employees e;
