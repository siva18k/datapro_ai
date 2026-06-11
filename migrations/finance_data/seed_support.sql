-- Support seed (aligned with 1_3 column names)
SET search_path TO finance_data, public;

TRUNCATE TABLE finance_data.support_ticket_comments RESTART IDENTITY CASCADE;
TRUNCATE TABLE finance_data.support_tickets RESTART IDENTITY CASCADE;
TRUNCATE TABLE finance_data.support_agents RESTART IDENTITY CASCADE;
TRUNCATE TABLE finance_data.support_ticket_categories RESTART IDENTITY CASCADE;

INSERT INTO finance_data.support_ticket_categories (category_id, category_name, description) VALUES
(1, 'Billing', 'Billing and payment issues'),
(2, 'Technical Issue', 'Product or system technical problems'),
(3, 'Account Access', 'Login and account access'),
(4, 'Order Inquiry', 'Order status and shipping'),
(5, 'Product Feedback', 'Product suggestions and feedback');

INSERT INTO finance_data.support_agents (agent_id, employee_id, hire_date, is_active) VALUES
(5001, 1004, '2021-04-01', TRUE),
(5002, 1008, '2020-06-15', TRUE),
(5003, 1009, '2022-02-01', TRUE);

INSERT INTO finance_data.support_tickets (
    ticket_id, customer_id, category_id, agent_id, opened_at, closed_at, status, subject, description
)
SELECT
    7000 + seq AS ticket_id,
    (SELECT customer_id FROM finance_data.customer_profiles ORDER BY customer_id LIMIT 1 OFFSET (seq % 5)),
    ((seq % 5) + 1) AS category_id,
    5001 + (seq % 3) AS agent_id,
    TIMESTAMP '2024-02-01' + (seq * 3) * INTERVAL '1 day' AS opened_at,
    CASE WHEN seq % 4 = 0 THEN TIMESTAMP '2024-02-01' + (seq * 3 + 5) * INTERVAL '1 day' END AS closed_at,
    CASE WHEN seq % 4 = 0 THEN 'RESOLVED' WHEN seq % 3 = 0 THEN 'IN_PROGRESS' ELSE 'OPEN' END AS status,
    'Ticket #' || (7000 + seq),
    'Auto-generated support ticket seed record'
FROM generate_series(1, 15) AS seq;

INSERT INTO finance_data.support_ticket_comments (comment_id, ticket_id, agent_id, comment_text, commented_at)
SELECT
    9000 + seq,
    7001 + ((seq - 1) % 15),
    5001 + (seq % 3),
    'Comment #' || seq || ' on ticket ' || (7001 + ((seq - 1) % 15)),
    NOW() - (seq % 10) * INTERVAL '1 day'
FROM generate_series(1, 40) AS seq;
