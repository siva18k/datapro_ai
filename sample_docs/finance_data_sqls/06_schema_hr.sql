-- =====================================================
-- HR Domain Tables
-- =====================================================
CREATE TABLE myedw.hr_departments (
    department_id BIGINT PRIMARY KEY,
    department_name TEXT NOT NULL
);

CREATE TABLE myedw.hr_job_titles (
    job_title_id BIGINT PRIMARY KEY,
    job_title_name TEXT NOT NULL
);

CREATE TABLE myedw.hr_employees (
    employee_id BIGINT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    department_id BIGINT REFERENCES myedw.hr_departments(department_id),
    job_title_id BIGINT REFERENCES myedw.hr_job_titles(job_title_id),
    hire_date DATE NOT NULL,
    salary NUMERIC(12,2) NOT NULL
);

CREATE TABLE myedw.hr_payroll (
    payroll_id BIGINT PRIMARY KEY,
    employee_id BIGINT REFERENCES myedw.hr_employees(employee_id),
    pay_period_start DATE NOT NULL,
    pay_period_end DATE NOT NULL,
    gross_pay NUMERIC(12,2),
    tax_withheld NUMERIC(12,2),
    net_pay NUMERIC(12,2)
);

CREATE TABLE myedw.hr_performance_reviews (
    review_id BIGINT PRIMARY KEY,
    employee_id BIGINT REFERENCES myedw.hr_employees(employee_id),
    review_year INT NOT NULL,
    rating NUMERIC(2,1),
    reviewer_id BIGINT REFERENCES myedw.hr_employees(employee_id),
    comments TEXT
)
