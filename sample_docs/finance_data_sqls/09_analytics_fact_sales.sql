--problem with sql
truncate table myedw.analytics_fact_sales_daily;
insert into myedw.analytics_fact_sales_daily (date_id, product_id, channel_id, order_count, revenue_amount)
select rc.date_id,soi.product_id, so.channel_id, count(soi.order_id ) order_count, soi.line_total revenue_amount
from myedw.sales_orders so
join myedw.sales_order_items soi on so.order_id=soi.order_id 
join myedw.reference_calendar rc on LEFT(so.order_date::text, 10)=LEFT(rc.date_id::text, 10)
group by rc.date_id, soi.product_id, so.channel_id

