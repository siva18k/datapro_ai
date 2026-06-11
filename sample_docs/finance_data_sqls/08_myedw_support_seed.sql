-- =====================================================
--  Phase 7: Support Domain (Structure + Seed)
--  Schema: myedw
-- =====================================================

-- Clean up
DROP TABLE IF EXISTS myedw.support_ticket_comments CASCADE;
DROP TABLE IF EXISTS myedw.support_tickets CASCADE;
DROP TABLE IF EXISTS myedw.support_ticket_categories CASCADE;
DROP TABLE IF EXISTS myedw.support_agents CASCADE;

-- =====================================================
-- 1️⃣ Support Agents Created in 1_3
-- =====================================================
/*CREATE TABLE myedw.support_agents (
    agent_id        BIGINT PRIMARY KEY,
    employee_id     BIGINT REFERENCES myedw.hr_employees(employee_id),
    hire_date       DATE NOT NULL,
    active_flag     BOOLEAN DEFAULT TRUE
);
*/
INSERT INTO myedw.support_agents (agent_id, employee_id, hire_date, active_flag) VALUES
(5001, 1004, '2021-04-01', TRUE),
(5002, 1008, '2020-06-15', TRUE),
(5003, 1009, '2022-02-01', TRUE);

-- =====================================================
-- 2️⃣ Ticket Categories Created in 1_3
-- =====================================================
/*CREATE TABLE myedw.support_ticket_categories (
    category_id     BIGINT PRIMARY KEY,
    category_name   TEXT NOT NULL UNIQUE
);
*/
INSERT INTO myedw.support_ticket_categories (category_id, category_name) VALUES
(1, 'Billing'),
(2, 'Technical Issue'),
(3, 'Account Access'),
(4, 'Order Inquiry'),
(5, 'Product Feedback');

-- =====================================================
-- 3️⃣ Support Tickets create again
-- =====================================================
drop table 
CREATE TABLE myedw.support_tickets (
    ticket_id       BIGINT PRIMARY KEY,
    customer_id     BIGINT REFERENCES myedw.customer_profiles(customer_id),
    category_id     BIGINT NOT NULL REFERENCES myedw.support_ticket_categories(category_id),
    agent_id        BIGINT REFERENCES myedw.support_agents(agent_id),
    opened_date     DATE NOT NULL,
    closed_date     DATE,
    status          TEXT CHECK (status IN ('Open','In Progress','Resolved','Closed')),
    priority        TEXT CHECK (priority IN ('Low','Medium','High','Critical')),
    subject         TEXT,
    description     TEXT
);

INSERT INTO myedw.support_tickets (
    ticket_id, customer_id, category_id, agent_id,
    opened_date, closed_date, status, priority, subject, description
)
SELECT
    7000 + seq AS ticket_id,
    (SELECT customer_id FROM myedw.customer_profiles ORDER BY customer_id LIMIT 1 OFFSET (seq % 5)) AS customer_id,
    ((seq % 5) + 1) AS category_id,
    5001 + (seq % 3) AS agent_id,
    (DATE '2024-02-01' + (seq * 3))::date AS opened_date,
    CASE WHEN seq % 4 = 0 THEN (DATE '2024-02-01' + (seq * 3) + 5)::date END AS closed_date,
    CASE WHEN seq % 4 = 0 THEN 'Resolved'
         WHEN seq % 3 = 0 THEN 'In Progress'
         ELSE 'Open' END AS status,
    CASE WHEN seq % 5 = 0 THEN 'Critical'
         WHEN seq % 4 = 0 THEN 'High'
         WHEN seq % 3 = 0 THEN 'Medium'
         ELSE 'Low' END AS priority,
    CONCAT('Ticket #',7000+seq) AS subject,
    'Auto-generated support ticket seed record' AS description
FROM generate_series(1,15) AS seq;

-- =====================================================
-- 4️⃣ Ticket Comments
-- =====================================================
drop table
CREATE TABLE myedw.support_ticket_comments (
    comment_id      BIGINT PRIMARY KEY,
    ticket_id       BIGINT REFERENCES myedw.support_tickets(ticket_id),
    commenter_id    BIGINT REFERENCES myedw.hr_employees(employee_id),
    comment_date    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    comment_text    TEXT NOT NULL
);

INSERT INTO myedw.support_ticket_comments (
    comment_id, ticket_id, commenter_id, comment_date, comment_text
)
SELECT
    9000 + seq AS comment_id,
    7001 + ((seq - 1) % 15) AS ticket_id,   -- ✅ aligned with ticket_id 7001–7015
    1001 + (seq % 10) AS commenter_id,
    NOW() - ((seq % 10) * INTERVAL '1 day') AS comment_date,
    CONCAT('Comment #', seq, ' on ticket ', 7001 + ((seq - 1) % 15))
FROM generate_series(1,40) AS seq;

-- Validation
SELECT 'Comments', COUNT(*) FROM myedw.support_ticket_comments;

-- =====================================================
-- 5️⃣ Validation
-- =====================================================
SELECT 'Agents', COUNT(*) FROM myedw.support_agents
UNION ALL SELECT 'Categories', COUNT(*) FROM myedw.support_ticket_categories
UNION ALL SELECT 'Tickets', COUNT(*) FROM myedw.support_tickets
UNION ALL SELECT 'Comments', COUNT(*) FROM myedw.support_ticket_comments;

