-- ===============================================================
-- 01_MYEDW_INVENTORY_DDL.SQL
-- Complete DDL for Inventory Domain
-- ===============================================================

SET search_path TO myedw, public;

-- ===============================================================
-- DROP EXISTING TABLES (safe order)
-- ===============================================================
DROP TABLE IF EXISTS myedw.inventory_stock_levels CASCADE;
DROP TABLE IF EXISTS myedw.inventory_products CASCADE;
DROP TABLE IF EXISTS myedw.inventory_locations CASCADE;
DROP TABLE IF EXISTS myedw.inventory_categories CASCADE;

-- ===============================================================
-- 1️⃣ INVENTORY CATEGORIES
-- ===============================================================
CREATE TABLE myedw.inventory_categories (
    category_id      BIGSERIAL PRIMARY KEY,
    category_name    TEXT NOT NULL UNIQUE,
    description      TEXT
);

COMMENT ON TABLE myedw.inventory_categories IS 'Master list of product categories';
COMMENT ON COLUMN myedw.inventory_categories.category_name IS 'Unique name of category';
COMMENT ON COLUMN myedw.inventory_categories.description IS 'Optional description of category';

-- ===============================================================
-- 2️⃣ INVENTORY LOCATIONS (Warehouses)
-- ===============================================================
CREATE TABLE myedw.inventory_locations (
    location_id   BIGSERIAL PRIMARY KEY,
    location_name TEXT NOT NULL UNIQUE,
    city          TEXT NOT NULL,
    country_code  TEXT NOT NULL,
    capacity      INT DEFAULT 0
);

COMMENT ON TABLE myedw.inventory_locations IS 'Physical warehouse or storage locations';
COMMENT ON COLUMN myedw.inventory_locations.capacity IS 'Storage capacity in product units';

-- ===============================================================
-- 3️⃣ INVENTORY PRODUCTS
-- ===============================================================
CREATE TABLE myedw.inventory_products (
    product_id   BIGSERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    category_id  BIGINT REFERENCES myedw.inventory_categories(category_id) ON DELETE SET NULL,
    sku          TEXT UNIQUE,
    unit_price   NUMERIC(10,2) NOT NULL,
    cost_price   NUMERIC(10,2),
    is_active    BOOLEAN DEFAULT TRUE
);

COMMENT ON TABLE myedw.inventory_products IS 'Catalog of sellable or stocked items';
COMMENT ON COLUMN myedw.inventory_products.sku IS 'Unique Stock Keeping Unit identifier';
COMMENT ON COLUMN myedw.inventory_products.category_id IS 'FK to inventory_categories';

-- ===============================================================
-- 4️⃣ INVENTORY STOCK LEVELS
-- ===============================================================
CREATE TABLE myedw.inventory_stock_levels (
    stock_id          BIGSERIAL PRIMARY KEY,
    location_id       BIGINT NOT NULL REFERENCES myedw.inventory_locations(location_id) ON DELETE CASCADE,
    product_id        BIGINT NOT NULL REFERENCES myedw.inventory_products(product_id) ON DELETE CASCADE,
    quantity_on_hand  INT NOT NULL DEFAULT 0,
    reorder_level     INT NOT NULL DEFAULT 10,
    last_updated      TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_inventory_stock UNIQUE (location_id, product_id)
);

COMMENT ON TABLE myedw.inventory_stock_levels IS 'Tracks on-hand and reorder stock quantities by warehouse and product';
COMMENT ON COLUMN myedw.inventory_stock_levels.reorder_level IS 'Threshold triggering restock process';
COMMENT ON COLUMN myedw.inventory_stock_levels.last_updated IS 'Timestamp of last stock update';

-- ===============================================================
-- ✅ Verify creation
-- ===============================================================
SELECT table_name
FROM information_schema.tables
WHERE table_schema='myedw' AND table_name LIKE 'inventory_%'
ORDER BY table_name;

