-- Agentic AI All-in-One Bootstrap (EDW + Docs + Registry + Seeds)
-- Schema: edw
CREATE SCHEMA IF NOT EXISTS edw;
SET search_path TO edw;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Reference tables
CREATE TABLE IF NOT EXISTS reference_currencies (currency_code text PRIMARY KEY, currency_name text NOT NULL, symbol text);
CREATE TABLE IF NOT EXISTS reference_countries (country_code text PRIMARY KEY, country_name text NOT NULL, iso3 text, currency_code text REFERENCES reference_currencies(currency_code));
CREATE TABLE IF NOT EXISTS reference_states (state_id bigserial PRIMARY KEY, state_code text, state_name text NOT NULL, country_code text NOT NULL REFERENCES reference_countries(country_code));
CREATE TABLE IF NOT EXISTS reference_cities (city_id bigserial PRIMARY KEY, city_name text NOT NULL, state_id bigint REFERENCES reference_states(state_id), country_code text NOT NULL REFERENCES reference_countries(country_code));
CREATE TABLE IF NOT EXISTS reference_calendar (date_id date PRIMARY KEY, year int, quarter int, month int, day int, week_of_year int, is_weekend boolean);
CREATE TABLE IF NOT EXISTS reference_units_of_measure (uom_code text PRIMARY KEY, description text NOT NULL);

-- Security
CREATE TABLE IF NOT EXISTS sec_users (user_id bigserial PRIMARY KEY, username text UNIQUE NOT NULL, email text UNIQUE NOT NULL, is_active boolean DEFAULT true, created_at timestamp DEFAULT now());
CREATE TABLE IF NOT EXISTS sec_roles (role_id bigserial PRIMARY KEY, role_name text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS sec_user_roles (user_id bigint REFERENCES sec_users(user_id) ON DELETE CASCADE, role_id bigint REFERENCES sec_roles(role_id) ON DELETE CASCADE, PRIMARY KEY (user_id, role_id));

-- Customers
CREATE TABLE IF NOT EXISTS customer_profiles (customer_id bigserial PRIMARY KEY, customer_code text UNIQUE, first_name text, last_name text, email text, phone text, created_date date REFERENCES reference_calendar(date_id), country_code text REFERENCES reference_countries(country_code));
CREATE TABLE IF NOT EXISTS customer_addresses (address_id bigserial PRIMARY KEY, customer_id bigint NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE, line1 text NOT NULL, line2 text, city_id bigint REFERENCES reference_cities(city_id), postal_code text, country_code text NOT NULL REFERENCES reference_countries(country_code), is_primary boolean DEFAULT false);
CREATE TABLE IF NOT EXISTS customer_preferences (pref_id bigserial PRIMARY KEY, customer_id bigint NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE, prefers_email boolean DEFAULT true, prefers_sms boolean DEFAULT false);
CREATE TABLE IF NOT EXISTS customer_segments (segment_id bigserial PRIMARY KEY, segment_name text UNIQUE NOT NULL, description text);
CREATE TABLE IF NOT EXISTS customer_segments_bridge (customer_id bigint NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE, segment_id bigint NOT NULL REFERENCES customer_segments(segment_id) ON DELETE CASCADE, assigned_date date REFERENCES reference_calendar(date_id), PRIMARY KEY (customer_id, segment_id));
CREATE TABLE IF NOT EXISTS customer_accounts (account_id bigserial PRIMARY KEY, customer_id bigint NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE, account_number text UNIQUE NOT NULL, opened_date date REFERENCES reference_calendar(date_id), status text CHECK (status IN ('ACTIVE','SUSPENDED','CLOSED')) DEFAULT 'ACTIVE');
CREATE TABLE IF NOT EXISTS customer_loyalty_points (customer_id bigint PRIMARY KEY REFERENCES customer_profiles(customer_id) ON DELETE CASCADE, points_balance bigint NOT NULL DEFAULT 0);

-- Inventory
CREATE TABLE IF NOT EXISTS inventory_product_categories (category_id bigserial PRIMARY KEY, category_name text NOT NULL, parent_id bigint REFERENCES inventory_product_categories(category_id));
CREATE TABLE IF NOT EXISTS inventory_products (product_id bigserial PRIMARY KEY, sku text UNIQUE NOT NULL, product_name text NOT NULL, category_id bigint REFERENCES inventory_product_categories(category_id), uom_code text REFERENCES reference_units_of_measure(uom_code), unit_weight_kg numeric(10,3));
CREATE TABLE IF NOT EXISTS inventory_warehouses (warehouse_id bigserial PRIMARY KEY, warehouse_code text UNIQUE NOT NULL, warehouse_name text NOT NULL, country_code text REFERENCES reference_countries(country_code));
CREATE TABLE IF NOT EXISTS inventory_locations (location_id bigserial PRIMARY KEY, warehouse_id bigint NOT NULL REFERENCES inventory_warehouses(warehouse_id) ON DELETE CASCADE, location_code text NOT NULL, description text);
CREATE TABLE IF NOT EXISTS inventory_suppliers (supplier_id bigserial PRIMARY KEY, supplier_code text UNIQUE NOT NULL, supplier_name text NOT NULL, country_code text REFERENCES reference_countries(country_code));
CREATE TABLE IF NOT EXISTS inventory_product_suppliers (product_id bigint NOT NULL REFERENCES inventory_products(product_id) ON DELETE CASCADE, supplier_id bigint NOT NULL REFERENCES inventory_suppliers(supplier_id) ON DELETE CASCADE, lead_time_days int, PRIMARY KEY (product_id, supplier_id));
CREATE TABLE IF NOT EXISTS inventory_price_lists (price_list_id bigserial PRIMARY KEY, price_list_name text NOT NULL, currency_code text REFERENCES reference_currencies(currency_code), effective_date date REFERENCES reference_calendar(date_id), status text CHECK (status IN ('ACTIVE','EXPIRED')) DEFAULT 'ACTIVE');
CREATE TABLE IF NOT EXISTS inventory_product_prices (product_id bigint NOT NULL REFERENCES inventory_products(product_id) ON DELETE CASCADE, price_list_id bigint NOT NULL REFERENCES inventory_price_lists(price_list_id) ON DELETE CASCADE, price numeric(18,2) NOT NULL, PRIMARY KEY (product_id, price_list_id));

-- Sales
CREATE TABLE IF NOT EXISTS sales_channels (channel_id bigserial PRIMARY KEY, channel_name text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS sales_orders (order_id bigserial PRIMARY KEY, order_number text UNIQUE NOT NULL, customer_id bigint NOT NULL REFERENCES customer_profiles(customer_id), order_date date NOT NULL REFERENCES reference_calendar(date_id), channel_id bigint REFERENCES sales_channels(channel_id), currency_code text REFERENCES reference_currencies(currency_code), status text CHECK (status IN ('NEW','ALLOCATED','SHIPPED','RETURNED','CANCELLED')) DEFAULT 'NEW');
CREATE TABLE IF NOT EXISTS sales_order_items (order_item_id bigserial PRIMARY KEY, order_id bigint NOT NULL REFERENCES sales_orders(order_id) ON DELETE CASCADE, product_id bigint NOT NULL REFERENCES inventory_products(product_id), quantity numeric(18,3) NOT NULL, unit_price numeric(18,2) NOT NULL, discount_amount numeric(18,2) DEFAULT 0);
CREATE TABLE IF NOT EXISTS sales_shipments (shipment_id bigserial PRIMARY KEY, order_id bigint NOT NULL REFERENCES sales_orders(order_id), ship_date date REFERENCES reference_calendar(date_id), carrier text, tracking_number text);
CREATE TABLE IF NOT EXISTS sales_shipment_items (shipment_item_id bigserial PRIMARY KEY, shipment_id bigint NOT NULL REFERENCES sales_shipments(shipment_id) ON DELETE CASCADE, order_item_id bigint NOT NULL REFERENCES sales_order_items(order_item_id), quantity numeric(18,3) NOT NULL);
CREATE TABLE IF NOT EXISTS sales_returns (return_id bigserial PRIMARY KEY, order_id bigint NOT NULL REFERENCES sales_orders(order_id), return_date date REFERENCES reference_calendar(date_id), reason text, refund_amount numeric(18,2));
CREATE TABLE IF NOT EXISTS sales_invoices (invoice_id bigserial PRIMARY KEY, invoice_number text UNIQUE NOT NULL, order_id bigint NOT NULL REFERENCES sales_orders(order_id), invoice_date date REFERENCES reference_calendar(date_id), total_amount numeric(18,2) NOT NULL, currency_code text REFERENCES reference_currencies(currency_code));
CREATE TABLE IF NOT EXISTS sales_invoice_items (invoice_item_id bigserial PRIMARY KEY, invoice_id bigint NOT NULL REFERENCES sales_invoices(invoice_id) ON DELETE CASCADE, order_item_id bigint REFERENCES sales_order_items(order_item_id), line_amount numeric(18,2) NOT NULL);
CREATE TABLE IF NOT EXISTS sales_payment_methods (payment_method_id bigserial PRIMARY KEY, method_name text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS sales_payments (payment_id bigserial PRIMARY KEY, invoice_id bigint NOT NULL REFERENCES sales_invoices(invoice_id), payment_date date REFERENCES reference_calendar(date_id), amount numeric(18,2) NOT NULL, payment_method_id bigint REFERENCES sales_payment_methods(payment_method_id), currency_code text REFERENCES reference_currencies(currency_code));

-- Marketing
CREATE TABLE IF NOT EXISTS marketing_campaigns (campaign_id bigserial PRIMARY KEY, campaign_name text NOT NULL, start_date date REFERENCES reference_calendar(date_id), end_date date REFERENCES reference_calendar(date_id), budget_amount numeric(18,2), currency_code text REFERENCES reference_currencies(currency_code));
CREATE TABLE IF NOT EXISTS marketing_campaign_channels (campaign_id bigint NOT NULL REFERENCES marketing_campaigns(campaign_id) ON DELETE CASCADE, channel_id bigint NOT NULL REFERENCES sales_channels(channel_id), PRIMARY KEY (campaign_id, channel_id));
CREATE TABLE IF NOT EXISTS marketing_leads (lead_id bigserial PRIMARY KEY, campaign_id bigint REFERENCES marketing_campaigns(campaign_id), customer_id bigint REFERENCES customer_profiles(customer_id), lead_date date REFERENCES reference_calendar(date_id), status text CHECK (status IN ('NEW','QUALIFIED','WON','LOST')) DEFAULT 'NEW');
CREATE TABLE IF NOT EXISTS marketing_web_events (event_id bigserial PRIMARY KEY, customer_id bigint REFERENCES customer_profiles(customer_id), event_time timestamp NOT NULL DEFAULT now(), event_type text, url text, payload jsonb);
CREATE TABLE IF NOT EXISTS marketing_promotions (promotion_id bigserial PRIMARY KEY, promo_code text UNIQUE NOT NULL, campaign_id bigint REFERENCES marketing_campaigns(campaign_id), start_date date REFERENCES reference_calendar(date_id), end_date date REFERENCES reference_calendar(date_id), status text CHECK (status IN ('PLANNED','ACTIVE','ENDED')) DEFAULT 'PLANNED');

-- Support
CREATE TABLE IF NOT EXISTS support_ticket_categories (category_id bigserial PRIMARY KEY, category_name text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS support_tickets (ticket_id bigserial PRIMARY KEY, customer_id bigint REFERENCES customer_profiles(customer_id), category_id bigint REFERENCES support_ticket_categories(category_id), opened_time timestamp NOT NULL DEFAULT now(), status text CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','CLOSED')) DEFAULT 'OPEN', priority text CHECK (priority IN ('LOW','MEDIUM','HIGH','CRITICAL')) DEFAULT 'LOW');
CREATE TABLE IF NOT EXISTS support_ticket_updates (update_id bigserial PRIMARY KEY, ticket_id bigint NOT NULL REFERENCES support_tickets(ticket_id) ON DELETE CASCADE, update_time timestamp NOT NULL DEFAULT now(), update_text text);
CREATE TABLE IF NOT EXISTS support_tags (tag_id bigserial PRIMARY KEY, tag_name text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS support_ticket_tags (ticket_id bigint NOT NULL REFERENCES support_tickets(ticket_id) ON DELETE CASCADE, tag_id bigint NOT NULL REFERENCES support_tags(tag_id) ON DELETE CASCADE, PRIMARY KEY (ticket_id, tag_id));

-- Finance
CREATE TABLE IF NOT EXISTS finance_ledger_accounts (account_id bigserial PRIMARY KEY, account_code text UNIQUE NOT NULL, account_name text NOT NULL, account_type text CHECK (account_type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')) NOT NULL);
CREATE TABLE IF NOT EXISTS finance_journal_entries (journal_id bigserial PRIMARY KEY, journal_date date REFERENCES reference_calendar(date_id), source_system text);
CREATE TABLE IF NOT EXISTS finance_journal_lines (line_id bigserial PRIMARY KEY, journal_id bigint NOT NULL REFERENCES finance_journal_entries(journal_id) ON DELETE CASCADE, account_id bigint NOT NULL REFERENCES finance_ledger_accounts(account_id), debit_amount numeric(18,2) DEFAULT 0, credit_amount numeric(18,2) DEFAULT 0, customer_id bigint REFERENCES customer_profiles(customer_id), product_id bigint REFERENCES inventory_products(product_id));
CREATE TABLE IF NOT EXISTS finance_ap_vendors (vendor_id bigserial PRIMARY KEY, vendor_code text UNIQUE NOT NULL, vendor_name text NOT NULL, country_code text REFERENCES reference_countries(country_code));
CREATE TABLE IF NOT EXISTS finance_ap_bills (bill_id bigserial PRIMARY KEY, vendor_id bigint NOT NULL REFERENCES finance_ap_vendors(vendor_id), bill_date date REFERENCES reference_calendar(date_id), due_date date REFERENCES reference_calendar(date_id), currency_code text REFERENCES reference_currencies(currency_code), status text CHECK (status IN ('OPEN','PAID','VOID')) DEFAULT 'OPEN');
CREATE TABLE IF NOT EXISTS finance_ap_bill_lines (bill_line_id bigserial PRIMARY KEY, bill_id bigint NOT NULL REFERENCES finance_ap_bills(bill_id) ON DELETE CASCADE, account_id bigint NOT NULL REFERENCES finance_ledger_accounts(account_id), line_amount numeric(18,2) NOT NULL, description text);

-- Analytics
CREATE TABLE IF NOT EXISTS analytics_fact_sales_daily (date_id date NOT NULL REFERENCES reference_calendar(date_id), product_id bigint NOT NULL REFERENCES inventory_products(product_id), channel_id bigint REFERENCES sales_channels(channel_id), order_count bigint NOT NULL DEFAULT 0, revenue_amount numeric(18,2) NOT NULL DEFAULT 0, PRIMARY KEY (date_id, product_id, channel_id));

-- HR helper
CREATE TABLE IF NOT EXISTS hr_employees (employee_id bigserial PRIMARY KEY, first_name text NOT NULL, last_name text NOT NULL, email text, department text DEFAULT 'HR', country_code text REFERENCES reference_countries(country_code), hire_date date REFERENCES reference_calendar(date_id));

-- Doc Core
CREATE TABLE IF NOT EXISTS doc_documents (doc_id bigserial PRIMARY KEY, doc_type text NOT NULL, title text NOT NULL, mime_type text NOT NULL DEFAULT 'application/pdf', source_system text, storage_url text, sha256_hex text, size_bytes bigint, language text DEFAULT 'en', received_at timestamp DEFAULT now(), status text DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED','DELETED')));
CREATE TABLE IF NOT EXISTS doc_document_versions (version_id bigserial PRIMARY KEY, doc_id bigint NOT NULL REFERENCES doc_documents(doc_id) ON DELETE CASCADE, version_no int NOT NULL DEFAULT 1, uploaded_at timestamp NOT NULL DEFAULT now(), storage_url text, sha256_hex text, size_bytes bigint, notes text, UNIQUE (doc_id, version_no));
CREATE TABLE IF NOT EXISTS doc_pages (page_id bigserial PRIMARY KEY, version_id bigint NOT NULL REFERENCES doc_document_versions(version_id) ON DELETE CASCADE, page_number int NOT NULL, text_content text, text_md5_hex text, ocr_confidence numeric(5,2), width_pts numeric(10,2), height_pts numeric(10,2), UNIQUE (version_id, page_number));
CREATE TABLE IF NOT EXISTS doc_annotations (annotation_id bigserial PRIMARY KEY, version_id bigint NOT NULL REFERENCES doc_document_versions(version_id) ON DELETE CASCADE, page_number int, key text NOT NULL, value text NOT NULL, bbox jsonb, confidence numeric(5,2));
CREATE TABLE IF NOT EXISTS doc_page_embeddings (embedding_id bigserial PRIMARY KEY, version_id bigint NOT NULL REFERENCES doc_document_versions(version_id) ON DELETE CASCADE, page_number int NOT NULL, embedding float8[] NOT NULL, model text DEFAULT 'demo-bert-384', created_at timestamp DEFAULT now(), UNIQUE (version_id, page_number));

-- Dept Registry
CREATE TABLE IF NOT EXISTS doc_repositories (repo_id bigserial PRIMARY KEY, repo_name text UNIQUE NOT NULL, repo_type text NOT NULL CHECK (repo_type IN ('filesystem','s3','sharepoint','gdrive','docdb')), base_url text NOT NULL, description text, is_active boolean NOT NULL DEFAULT true, created_at timestamp NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS doc_collections (collection_id bigserial PRIMARY KEY, repo_id bigint NOT NULL REFERENCES doc_repositories(repo_id) ON DELETE CASCADE, department text NOT NULL, collection_key text NOT NULL, path_prefix text, is_active boolean NOT NULL DEFAULT true, UNIQUE (repo_id, department, collection_key));
CREATE TABLE IF NOT EXISTS doc_entity_links (link_id bigserial PRIMARY KEY, doc_id bigint NOT NULL REFERENCES doc_documents(doc_id) ON DELETE CASCADE, entity_table text NOT NULL, entity_pk bigint NOT NULL, role text, created_at timestamp NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS doc_tags (tag_id bigserial PRIMARY KEY, tag_key text UNIQUE NOT NULL, tag_label text NOT NULL, description text);
CREATE TABLE IF NOT EXISTS doc_document_tags (doc_id bigint NOT NULL REFERENCES doc_documents(doc_id) ON DELETE CASCADE, tag_id bigint NOT NULL REFERENCES doc_tags(tag_id) ON DELETE CASCADE, PRIMARY KEY (doc_id, tag_id));
CREATE TABLE IF NOT EXISTS doc_acl (acl_id bigserial PRIMARY KEY, doc_id bigint NOT NULL REFERENCES doc_documents(doc_id) ON DELETE CASCADE, principal_type text NOT NULL CHECK (principal_type IN ('role','user','department')), principal_key text NOT NULL, permission text NOT NULL CHECK (permission IN ('READ','WRITE','ADMIN')), created_at timestamp NOT NULL DEFAULT now(), UNIQUE (doc_id, principal_type, principal_key, permission));

-- Minimal indexes
CREATE INDEX IF NOT EXISTS idx_sales_orders_customer_date ON sales_orders(customer_id, order_date);
CREATE INDEX IF NOT EXISTS idx_doc_pages_text_gin ON doc_pages USING gin (to_tsvector('english', coalesce(text_content,'')));
CREATE INDEX IF NOT EXISTS idx_doc_links_entity ON doc_entity_links(entity_table, entity_pk);

-- Seeds (short version to keep file compact here)
INSERT INTO reference_currencies VALUES ('USD','US Dollar','$') ON CONFLICT DO NOTHING;
INSERT INTO reference_currencies VALUES ('EUR','Euro','€') ON CONFLICT DO NOTHING;
INSERT INTO reference_countries VALUES ('US','United States','USA','USD') ON CONFLICT DO NOTHING;
INSERT INTO reference_countries VALUES ('DE','Germany','DEU','EUR') ON CONFLICT DO NOTHING;
INSERT INTO reference_units_of_measure VALUES ('EA','Each') ON CONFLICT DO NOTHING;

WITH d AS (
  SELECT gs::date AS d FROM generate_series(CURRENT_DATE - INTERVAL '5 years', CURRENT_DATE + INTERVAL '5 years', '1 day') gs
)
INSERT INTO reference_calendar(date_id, year, quarter, month, day, week_of_year, is_weekend)
SELECT d, EXTRACT(YEAR FROM d)::int, EXTRACT(QUARTER FROM d)::int, EXTRACT(MONTH FROM d)::int, EXTRACT(DAY FROM d)::int, EXTRACT(WEEK FROM d)::int, EXTRACT(ISODOW FROM d) IN (6,7)
FROM d ON CONFLICT DO NOTHING;

INSERT INTO sales_channels(channel_name) VALUES ('Web'),('Store'),('Marketplace') ON CONFLICT DO NOTHING;
INSERT INTO inventory_product_categories(category_name) VALUES ('All Products') ON CONFLICT DO NOTHING;
INSERT INTO inventory_products(sku, product_name, category_id, uom_code, unit_weight_kg)
SELECT 'SKU'||to_char(gs,'FM000000'),'Product '||gs,(SELECT category_id FROM inventory_product_categories LIMIT 1),'EA',1.0 FROM generate_series(1,5000) gs
ON CONFLICT DO NOTHING;

INSERT INTO customer_profiles(customer_code, first_name, last_name, email, phone, created_date, country_code)
SELECT 'C'||to_char(gs,'FM000000'), 'Cust'||gs, 'User'||gs, 'cust'||gs||'@example.com', '+1-555-'||to_char(gs%10000,'FM0000'), CURRENT_DATE - ((random()*700)::int), 'US'
FROM generate_series(1,10000) gs ON CONFLICT DO NOTHING;

INSERT INTO sales_orders(order_number, customer_id, order_date, channel_id, currency_code, status)
SELECT 'SO'||to_char(gs,'FM000000'),
       (SELECT customer_id FROM customer_profiles ORDER BY random() LIMIT 1),
       CURRENT_DATE - ((random()*500)::int),
       (SELECT channel_id FROM sales_channels ORDER BY random() LIMIT 1),
       'USD',
       (ARRAY['NEW','SHIPPED','CANCELLED'])[1+(random()*2)::int]
FROM generate_series(1,50000) gs;

INSERT INTO sales_order_items(order_id, product_id, quantity, unit_price, discount_amount)
SELECT o.order_id,
       (SELECT product_id FROM inventory_products ORDER BY random() LIMIT 1),
       1 + (random()*5)::int,
       round((5 + random()*300)::numeric,2),
       round(((CASE WHEN random()<0.15 THEN random()*15 ELSE 0 END))::numeric,2)
FROM sales_orders o, generate_series(1, (1 + (random()*3)::int)) s(n);

INSERT INTO sales_invoices(invoice_number, order_id, invoice_date, total_amount, currency_code)
SELECT 'INV'||to_char(o.order_id,'FM000000'), o.order_id, o.order_date + ((random()*7)::int),
       round((SELECT COALESCE(SUM(oi.quantity*oi.unit_price - oi.discount_amount),0) FROM sales_order_items oi WHERE oi.order_id=o.order_id),2),
       'USD'
FROM sales_orders o WHERE o.status <> 'CANCELLED';

INSERT INTO sales_invoice_items(invoice_id, order_item_id, line_amount)
SELECT i.invoice_id, oi.order_item_id, round(oi.quantity*oi.unit_price - oi.discount_amount,2)
FROM sales_invoices i JOIN sales_order_items oi ON oi.order_id=i.order_id;

INSERT INTO sales_payment_methods(method_name) VALUES ('Card'),('Cash'),('ACH') ON CONFLICT DO NOTHING;
INSERT INTO sales_payments(invoice_id, payment_date, amount, payment_method_id, currency_code)
SELECT i.invoice_id, i.invoice_date + ((random()*14)::int), round(i.total_amount * (CASE WHEN random()<0.1 THEN 0.5 ELSE 1.0 END),2),
       (SELECT payment_method_id FROM sales_payment_methods ORDER BY random() LIMIT 1), 'USD'
FROM sales_invoices i;

-- Minimal doc registry seeds
INSERT INTO doc_repositories(repo_name, repo_type, base_url) VALUES
 ('HR Share','filesystem','file:///dept/hr'),
 ('Marketing S3','s3','s3://corp-marketing'),
 ('Support Share','filesystem','file:///dept/support'),
 ('DocDB Primary','docdb','docdb://primary')
ON CONFLICT (repo_name) DO NOTHING;

-- Views
CREATE OR REPLACE VIEW v_docs_by_department AS
SELECT c.department, d.doc_type, COUNT(*) AS doc_count
FROM doc_documents d JOIN doc_collections c ON c.collection_id=d.collection_id
GROUP BY c.department, d.doc_type
ORDER BY c.department, d.doc_type;

CREATE OR REPLACE FUNCTION fn_doc_search(q text)
RETURNS TABLE(doc_id bigint, version_id bigint, page_number int, snippet text) AS
$$
  SELECT dv.doc_id, p.version_id, p.page_number,
         ts_headline('english', p.text_content, plainto_tsquery('english', q))
  FROM doc_pages p
  JOIN doc_document_versions dv ON dv.version_id=p.version_id
  WHERE to_tsvector('english', coalesce(p.text_content,'')) @@ plainto_tsquery('english', q);
$$ LANGUAGE sql STABLE;

-- Read-only role
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edw_ro') THEN
    CREATE ROLE edw_ro LOGIN PASSWORD 'edw_ro_pass';
    GRANT USAGE ON SCHEMA edw TO edw_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA edw TO edw_ro;
    ALTER DEFAULT PRIVILEGES IN SCHEMA edw GRANT SELECT ON TABLES TO edw_ro;
  END IF;
END$$;
