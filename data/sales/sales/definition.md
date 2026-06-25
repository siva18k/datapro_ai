# Sales Dataset

## What this dataset is
The Sales dataset captures all transactional and operational data related to sales activities, including orders, invoices, payments, shipments, and returns. It supports financial analysis, customer behavior tracking, and operational performance monitoring.

January to March is Q1
April to June is Q2
July to September is Q3
October to December is Q4.
Financial Year and FY are same, FY2024 is financial year 2024 which means Q1 to Q4.


## Core tables

- **`finance_data.analytics_fact_sales_daily`**: Aggregated daily sales metrics by channel and product.
  - Columns: `channel_id`, `date_id`, `order_count`, `product_id`, `revenue_amount`

- **`finance_data.reference_sales_channels`**: Lookup table for sales channels.
  - Columns: `channel_id`, `channel_name`, `description`

- **`finance_data.sales_invoices`**: Detailed invoice records.
  - Columns: `currency_code`, `due_date`, `invoice_date`, `invoice_id`, `order_id`, `paid_amount`, `tax_amount`, `total_amount`

- **`finance_data.sales_order_items`**: Line items for each order.
  - Columns: `discount_amount`, `line_total`, `order_id`, `order_item_id`, `product_id`, `quantity`, `unit_price`

- **`finance_data.sales_orders`**: Core order records.
  - Columns: `channel_id`, `currency_code`, `customer_id`, `order_date`, `order_id`, `payment_method_id`, `status`, `total_amount`

- **`finance_data.sales_payments`**: Payment transactions.
  - Columns: `amount`, `invoice_id`, `method_id`, `payment_date`, `payment_id`, `reference_no`

- **`finance_data.sales_returns`**: Returned orders and refunds.
  - Columns: `order_id`, `reason`, `refund_amount`, `return_date`, `return_id`

- **`finance_data.sales_shipments`**: Shipping details for orders.
  - Columns: `carrier`, `order_id`, `shipment_id`, `shipped_date`, `status`, `tracking_number`

## Common analytics patterns

- **Revenue by Channel**: Join `finance_data.analytics_fact_sales_daily` with `finance_data.reference_sales_channels` on `channel_id` to analyze performance by sales channel.
- **Order Fulfillment**: Combine `finance_data.sales_orders` with `finance_data.sales_shipments` on `order_id` to track delivery status.
- **Payment Analysis**: Use `finance_data.sales_invoices` and `finance_data.sales_payments` to reconcile payments against invoices.
- **Return Impact**: Join `finance_data.sales_orders` with `finance_data.sales_returns` to assess return rates and reasons.

## Caveats

- No explicit customer PII is stored in this dataset (customer details are referenced via `customer_id`).
- The `finance_data.analytics_fact_sales_daily` table is pre-aggregated and may not include all granular details found in transactional tables.
- Some tables (e.g., `sales_returns`) may have limited historical data due to implementation timing.

<!-- datapro:relationships:start -->
## Table relationships (auto-generated)

Join paths between cataloged tables (from database foreign keys and column naming). Use schema-qualified names in SQL. Refresh after catalog changes.

### Hub tables

- **`finance_data.reference_sales_channels`** — referenced by 2 join path(s); use as the central join target.
- **`finance_data.sales_orders`** — referenced by 4 join path(s); use as the central join target.

| From table | Column | To table | Column | Source |
| --- | --- | --- | --- | --- |
| `finance_data.analytics_fact_sales_daily` | `channel_id` | `finance_data.reference_sales_channels` | `channel_id` | database |
| `finance_data.sales_invoices` | `order_id` | `finance_data.sales_orders` | `order_id` | database |
| `finance_data.sales_order_items` | `order_id` | `finance_data.sales_orders` | `order_id` | database |
| `finance_data.sales_orders` | `channel_id` | `finance_data.reference_sales_channels` | `channel_id` | database |
| `finance_data.sales_payments` | `invoice_id` | `finance_data.sales_invoices` | `invoice_id` | database |
| `finance_data.sales_returns` | `order_id` | `finance_data.sales_orders` | `order_id` | database |
| `finance_data.sales_shipments` | `order_id` | `finance_data.sales_orders` | `order_id` | database |

### Join notes

- **finance_data.analytics_fact_sales_daily.channel_id** → **finance_data.reference_sales_channels.channel_id** — Foreign key — join `finance_data.analytics_fact_sales_daily.channel_id` to `finance_data.reference_sales_channels.channel_id`.
- **finance_data.sales_invoices.order_id** → **finance_data.sales_orders.order_id** — Foreign key — join `finance_data.sales_invoices.order_id` to `finance_data.sales_orders.order_id`.
- **finance_data.sales_order_items.order_id** → **finance_data.sales_orders.order_id** — Foreign key — join `finance_data.sales_order_items.order_id` to `finance_data.sales_orders.order_id`.
- **finance_data.sales_orders.channel_id** → **finance_data.reference_sales_channels.channel_id** — Foreign key — join `finance_data.sales_orders.channel_id` to `finance_data.reference_sales_channels.channel_id`.
- **finance_data.sales_payments.invoice_id** → **finance_data.sales_invoices.invoice_id** — Foreign key — join `finance_data.sales_payments.invoice_id` to `finance_data.sales_invoices.invoice_id`.
- **finance_data.sales_returns.order_id** → **finance_data.sales_orders.order_id** — Foreign key — join `finance_data.sales_returns.order_id` to `finance_data.sales_orders.order_id`.
- **finance_data.sales_shipments.order_id** → **finance_data.sales_orders.order_id** — Foreign key — join `finance_data.sales_shipments.order_id` to `finance_data.sales_orders.order_id`.

### Cataloged tables by role

**fact / dimension**: `finance_data.analytics_fact_sales_daily`, `finance_data.sales_invoices`, `finance_data.sales_order_items`, `finance_data.sales_orders`, `finance_data.sales_payments`, `finance_data.sales_returns`, `finance_data.sales_shipments`
**lookup**: `finance_data.reference_sales_channels`
<!-- datapro:relationships:end -->
