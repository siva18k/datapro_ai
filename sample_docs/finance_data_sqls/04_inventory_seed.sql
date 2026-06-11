-- ===============================================================
-- 02_MYEDW_INVENTORY_SEED.SQL
-- Populates Inventory Domain with Realistic Data
-- ===============================================================

SET search_path TO myedw, public;
truncate myedw.inventory_categories cascade;
truncate myedw.inventory_locations cascade;
truncate myedw.inventory_products cascade;
truncate myedw.inventory_stock_levels cascade; 
==============================
INSERT INTO 
-- ===============================================================
-- 1️⃣ INVENTORY CATEGORIES
-- ===============================================================
INSERT INTO myedw.inventory_categories (category_name, description)
VALUES
 ('Electronics','Devices and accessories'),
 ('Home & Kitchen','Appliances and utensils'),
 ('Books','Physical and digital books'),
 ('Clothing','Apparel and fashion'),
 ('Sports','Sports and outdoor equipment'),
 ('Health & Beauty','Personal care and fitness'),
 ('Toys','Children and hobby items'),
 ('Automotive','Vehicle parts and accessories'),
 ('Office','Office supplies and equipment'),
 ('Garden','Gardening and outdoor decor')
ON CONFLICT (category_name) DO NOTHING;

-- ===============================================================
-- 2️⃣ INVENTORY LOCATIONS
-- ===============================================================
INSERT INTO myedw.inventory_locations (location_name, city, country_code, capacity)
SELECT
    CONCAT('Warehouse-', g),
    (ARRAY['New York','Los Angeles','Chicago','Dallas','Miami','Seattle'])[1+(random()*5)::int],
    (ARRAY['US','CA','GB','DE','FR','IN'])[1+(random()*5)::int],
    (5000 + (random()*15000)::int)
FROM generate_series(1, 10) g
ON CONFLICT (location_name) DO NOTHING;

-- ===============================================================
-- 3️⃣ INVENTORY PRODUCTS
-- ===============================================================
INSERT INTO myedw.inventory_products (product_name, category_id, sku, unit_price, cost_price, is_active)
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =1),
    CONCAT('SKU-1', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('Apple','iGadget'),
    ('Samsung','SmartX'),
    ('Sony','BraviaX'),
    ('LG','UltraQ'),
    ('Dell','Inspire'),
    ('HP','Elite'),
    ('Bosch','PowerDrill'),
    ('Canon','PixSharp')
) AS x(brand,model) ON true
--Home & Kitchen
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =2),
    CONCAT('SKU-2', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('Bosch','WasherDryer'),
    ('Samsung','Refrigrator'),
    ('Samsung','WasherDryer'),
    ('LG','WasherDryer'),
    ('LG','Refrigrator'),
    ('Bosch','Refrigrator')
) AS x(brand,model) ON true
--Books
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =3),
    CONCAT('SKU-3', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('Amazon','TheInternetWalmart'),
    ('Wielly','WorldPhoneBook'),
    ('LinkedIn','SocialMedia'),
    ('Facebook','WhatsAppyGuide')
) AS x(brand,model) ON true
--Clothing
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =4),
    CONCAT('SKU-4', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('Nike','JordanT-XXL'),
    ('Nike','JordanT-XL'),
    ('Nike','Jordans'),
    ('Oaklay','SportsShorts'),
    ('Oaklay','RunningPants'),
    ('Puma','Socks'),
    ('Puma','GolfShirt'),
    ('Oaklay','GolfShirt')
) AS x(brand,model) ON true
--Sports
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =5),
    CONCAT('SKU-5', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('Nike','BasketBall'),
    ('Wilson','TennisRacket'),
    ('Wilson','TennisBalls'),
    ('Nke','GolfBalls'),
    ('Dunlop','TennisBalls'),
    ('DunLop','TennisTacket'),
    ('Puma','SoccerBall')
) AS x(brand,model) ON true
--Health & Beauty
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =6),
    CONCAT('SKU-6', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('Target','Shampoo'),
    ('Target','Lipstick'),
    ('Target','HAirColor'),
    ('Amazon','Shampoo'),
    ('Amazon','Lipstick'),
    ('Amazon','HAirColor'),
    ('Target','Asprin'),
    ('Amazon','Asprin')
) AS x(brand,model) ON true
--Toys
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =7),
    CONCAT('SKU-7', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('CarARus','MB350'),
    ('CarARus','PorcheCayane2025'),
    ('CarARus','Mustang'),
    ('CarARus','Pinto'),
    ('SuperCars','Ferarri'),
    ('SuperCars','Testarosa')
) AS x(brand,model) ON true
--Automotive
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =8),
    CONCAT('SKU-8', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('General','iAirGadget5Pins'),
    ('MobileOil','5W30'),
    ('MobileOil','10W40'),
    ('CarSheild','5PeiceCarMats'),
    ('Armoral','TireShineSpray')
) AS x(brand,model) ON true
--Office
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =9),
    CONCAT('SKU-9', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 3) g
JOIN (
  VALUES
    ('Staples','Office Chair'),
    ('Staples','Office Lamp'),
    ('Staples','Whiteboard With Stand 30 Inches')
) AS x(brand,model) ON true
--Garden
union ALL
SELECT
    CONCAT(x.brand, ' ', x.model),
    (SELECT category_id FROM myedw.inventory_categories where category_id =10),
    CONCAT('SKU-10', LPAD(ROW_NUMBER() OVER (ORDER BY x.brand, x.model, g)::text, 5, '0')) AS sku,
    round((10 + random()*990)::numeric,2), 
    round((5 + random()*500)::numeric,2),
    TRUE
FROM generate_series(1, 5) g
JOIN (
  VALUES
    ('Sundance','Patio Umblellas'),
    ('Lighthouse','Patio Lights'),
    ('MosquitoRpl','Mosquito Away'),
    ('WaterSupply','Copper Garden Hose'),
    ('WaterSupply','Long Distance Sprayer'),
    ('Moulcher','Small Garden Cart'),
    ('Moulcher','Large Garden Cart')
) AS x(brand,model) ON true
ON CONFLICT (sku) DO NOTHING;

-- ===============================================================
-- 4️⃣ INVENTORY STOCK LEVELS
-- ===============================================================
INSERT INTO myedw.inventory_stock_levels (location_id, product_id, quantity_on_hand, reorder_level, last_updated)
SELECT
    l.location_id,
    p.product_id,
    (50 + (random() * 500)::int) AS qty_on_hand,
    (10 + (random() * 40)::int) AS reorder_point,
    NOW() - ((random() * 100)::int || ' days')::interval AS last_updated
FROM myedw.inventory_locations l
CROSS JOIN myedw.inventory_products p;
-- ===============================================================
-- ✅ Sanity Checks
-- ===============================================================
SELECT COUNT(*) AS total_categories FROM myedw.inventory_categories;
SELECT COUNT(*) AS total_locations FROM myedw.inventory_locations;
SELECT COUNT(*) AS total_products FROM myedw.inventory_products;
SELECT COUNT(*) AS total_stock_records FROM myedw.inventory_stock_levels;

