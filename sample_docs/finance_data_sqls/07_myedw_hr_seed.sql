-- =====================================================
--  Phase 6: HR Domain Seed (v1.1)
--  Schema: myedw
--  Notes: Casted numeric rounding (PostgreSQL compatible)
-- =====================================================

-- Cleanup existing data
TRUNCATE TABLE myedw.hr_performance_reviews CASCADE;
TRUNCATE TABLE myedw.hr_payroll CASCADE;
TRUNCATE TABLE myedw.hr_employees CASCADE;
TRUNCATE TABLE myedw.hr_job_titles CASCADE;
TRUNCATE TABLE myedw.hr_departments CASCADE;

-- =====================================================
-- 1️⃣ Departments
-- =====================================================
INSERT INTO myedw.hr_departments (department_id, department_name) VALUES
(10, 'Finance'),
(20, 'Human Resources'),
(30, 'Sales'),
(40, 'IT'),
(50, 'Operations'),
(60, 'Marketing');

-- =====================================================
-- 2️⃣ Job Titles Seeded in 102-Section 4
-- =====================================================
/*
INSERT INTO myedw.hr_job_titles (job_title_id, job_title_name) VALUES
(100, 'Chief Executive Officer'),
(110, 'Finance Manager'),
(120, 'HR Manager'),
(130, 'Sales Manager'),
(140, 'IT Manager'),
(150, 'Operations Lead'),
(160, 'Marketing Lead'),
(170, 'Data Engineer'),
(180, 'Data Analyst'),
(190, 'Accountant');
*/
-- =====================================================
-- 3️⃣ Employees
-- =====================================================
INSERT INTO myedw.hr_employees (
    employee_id, first_name, last_name,
    department_id, job_title_id,
    hire_date, salary, email,phone, status_code, country_code
) VALUES
(1001, 'John',   'Doe',        10, 1, '2020-01-10', 85000, 'john.doe@demo.com','240-111-1212','ACTIVE','US'),
(1002, 'Mary',   'Smith',      20, 2, '2019-07-15', 78000, 'mary.smith@demo.com','240-111-1213', 'ACTIVE','US'),
(1003, 'Robert', 'Brown',      30, 3, '2021-03-12', 90000, 'robert.brown@demo.com','240-111-1214', 'ACTIVE','US'),
(1004, 'Linda',  'Garcia',     40, 4, '2018-09-20', 95000, 'linda.garcia@demo.com','240-111-1215', 'ACTIVE','US'),
(1005, 'James',  'Wilson',     50, 5, '2022-02-14', 72000, 'james.wilson@demo.com','240-111-1216', 'ACTIVE','US'),
(1006, 'Patricia','Miller',    60, 6, '2020-11-30', 70000, 'patricia.miller@demo.com','240-111-1217', 'ACTIVE','US'),
(1007, 'Michael','Taylor',     10, 7, '2021-06-18', 68000, 'michael.taylor@demo.com','240-111-1218', 'ACTIVE','US'),
(1008, 'Jennifer','Davis',     40, 7, '2019-04-05', 98000, 'jennifer.davis@demo.com','240-111-1218', 'ACTIVE','US'),
(1009, 'William','Anderson',   40, 7, '2020-12-11', 94000, 'william.anderson@demo.com','240-111-1219','ACTIVE','US'),
(1010, 'Susan',  'Thomas',     30, 8, '2022-01-05', 62000, 'susan.thomas@demo.com','240-111-1220', 'ACTIVE','US'),
(1011, 'Brian',  'Lane',     30, 8, '2022-01-05', 62000, 'brian.lane@demo.com','240-111-1221', 'LEAVE','US'),
(1012, 'Craig',  'Craig',     30, 8, '2022-01-05', 62000, 'craig.craig@demo.com','240-111-1222', 'TERMINATED','US'),
(1013, 'Moses',  'Johnson',     30, 8, '2022-01-05', 62000, 'moses.johnson@demo.com','240-111-1223', 'TERMINATED','US')
-- =====================================================
-- 4️⃣ Payroll (3 months per employee)
-- =====================================================
INSERT INTO myedw.hr_payroll (
    payroll_id, employee_id, pay_period_start, pay_period_end,
    gross_pay, tax_withheld, net_pay
)
SELECT
    (e.employee_id * 10 + p.seq) AS payroll_id,
    e.employee_id,
    DATE '2024-01-01' + (p.seq - 1) * 30 AS pay_period_start,
    DATE '2024-01-31' + (p.seq - 1) * 30 AS pay_period_end,
    ROUND((e.salary / 12)::numeric, 2) AS gross_pay,
    ROUND(((e.salary / 12) * 0.22)::numeric, 2) AS tax_withheld,
    ROUND(((e.salary / 12) * (1 - 0.22))::numeric, 2) AS net_pay
FROM myedw.hr_employees e
CROSS JOIN generate_series(1,3) AS p(seq);

-- =====================================================
-- 5️⃣ Performance Reviews (latest year)
-- =====================================================
drop table myedw.hr_performance_reviews ;
CREATE TABLE myedw.hr_performance_reviews (
    review_id BIGINT PRIMARY KEY,
    employee_id BIGINT REFERENCES myedw.hr_employees(employee_id),
    review_year INT NOT NULL,
    rating NUMERIC(2,1),
    reviewer_id BIGINT REFERENCES myedw.hr_employees(employee_id),
    comments TEXT
);
INSERT INTO myedw.hr_performance_reviews (
    review_id, employee_id, review_year, rating, reviewer_id, comments
)
SELECT
    employee_id AS review_id,
    employee_id,
    2024 AS review_year,
    ROUND((3.5 + (random() * 1.0))::numeric, 1) AS rating,
    CASE 
        WHEN department_id = 10 THEN 1001
        WHEN department_id = 20 THEN 1002
        WHEN department_id = 30 THEN 1003
        WHEN department_id = 40 THEN 1004
        ELSE 1001
    END AS reviewer_id,
    'Annual review seed data'
FROM myedw.hr_employees;

-- =====================================================
-- 6️⃣ Validation
-- =====================================================
SELECT 'Departments' AS table, COUNT(*) FROM myedw.hr_departments
UNION ALL SELECT 'Job Titles', COUNT(*) FROM myedw.hr_job_titles
UNION ALL SELECT 'Employees', COUNT(*) FROM myedw.hr_employees
UNION ALL SELECT 'Payroll', COUNT(*) FROM myedw.hr_payroll
UNION ALL SELECT 'Reviews', COUNT(*) FROM myedw.hr_performance_reviews;

SELECT COUNT(*) AS invalid_payroll_rows
FROM myedw.hr_payroll
WHERE ROUND(net_pay,2) <> ROUND(gross_pay - tax_withheld,2);

SELECT AVG(rating) AS avg_performance_rating