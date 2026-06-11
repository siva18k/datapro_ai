SET search_path TO finance_data, public;

TRUNCATE TABLE finance_data.analytics_fact_sales_daily;

INSERT INTO finance_data.analytics_fact_sales_daily (date_id, product_id, channel_id, order_count, revenue_amount)
SELECT
    rc.date_id,
    soi.product_id,
    so.channel_id,
    COUNT(DISTINCT so.order_id) AS order_count,
    SUM(soi.line_total) AS revenue_amount
FROM finance_data.sales_orders so
JOIN finance_data.sales_order_items soi ON so.order_id = soi.order_id
JOIN finance_data.reference_calendar rc ON so.order_date = rc.date_id
GROUP BY rc.date_id, soi.product_id, so.channel_id;
