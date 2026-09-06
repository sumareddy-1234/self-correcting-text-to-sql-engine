-- Database Seeding Script for Messy E-Commerce Schema
-- Intentional schema traps:
-- 1. customers PK is 'customer_id', but orders FK is 'cust_id'
-- 2. orders contains denormalized 'total_amount'
-- 3. customers.region is nullable

DROP TABLE IF EXISTS line_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    region VARCHAR(50) -- Nullable intentionally
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    cust_id INT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    order_date DATE NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00
);

CREATE TABLE line_items (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_name VARCHAR(100) NOT NULL,
    qty INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

-- Seed 150 Customers
DO $$
DECLARE
    regions TEXT[] := ARRAY['North', 'South', 'East', 'West', 'Central', 'Pacific', 'Midwest', 'Northwest', NULL];
    first_names TEXT[] := ARRAY['Alice', 'Bob', 'Charlie', 'Diana', 'Evan', 'Fiona', 'George', 'Hannah', 'Ian', 'Julia', 'Kevin', 'Laura', 'Michael', 'Nina', 'Oscar', 'Paula', 'Quinn', 'Rachel', 'Sam', 'Tina'];
    last_names TEXT[] := ARRAY['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin'];
    r_idx INT;
BEGIN
    FOR i IN 1..150 LOOP
        r_idx := ((i - 1) % 9) + 1;
        INSERT INTO customers (customer_id, name, region)
        VALUES (
            i,
            first_names[((i * 3) % 20) + 1] || ' ' || last_names[((i * 7) % 20) + 1],
            regions[r_idx]
        );
    END LOOP;
    PERFORM setval('customers_customer_id_seq', 150, true);
END $$;

-- Seed 600 Orders
DO $$
DECLARE
    start_date DATE := '2024-01-01';
    curr_cust_id INT;
    o_date DATE;
BEGIN
    FOR i IN 1..600 LOOP
        curr_cust_id := ((i * 13) % 150) + 1;
        o_date := start_date + ((i * 3) % 365);
        INSERT INTO orders (id, cust_id, order_date, total_amount)
        VALUES (i, curr_cust_id, o_date, 0.00);
    END LOOP;
    PERFORM setval('orders_id_seq', 600, true);
END $$;

-- Seed 1800 Line Items and update order total_amounts
DO $$
DECLARE
    products TEXT[] := ARRAY['Wireless Ergonomic Mouse', 'Mechanical Gaming Keyboard', '27-inch 4K Monitor', 'USB-C Multiport Hub', 'Noise-Canceling Headphones', 'Ergonomic Desk Chair', 'Standing Desk Converter', 'HD Webcam 1080p', 'Aluminum Laptop Stand', 'Portable External SSD 1TB'];
    prices NUMERIC[] := ARRAY[29.99, 89.99, 349.50, 45.00, 199.99, 250.00, 180.00, 65.00, 39.99, 110.00];
    p_idx INT;
    l_qty INT;
    l_price NUMERIC(10,2);
    target_order_id INT;
BEGIN
    FOR i IN 1..1800 LOOP
        target_order_id := ((i - 1) % 600) + 1;
        p_idx := ((i * 5) % 10) + 1;
        l_qty := ((i * 2) % 5) + 1;
        l_price := prices[p_idx];

        INSERT INTO line_items (id, order_id, product_name, qty, unit_price)
        VALUES (i, target_order_id, products[p_idx], l_qty, l_price);
    END LOOP;
    PERFORM setval('line_items_id_seq', 1800, true);

    -- Update denormalized total_amount in orders table
    UPDATE orders o
    SET total_amount = sub.sum_amt
    FROM (
        SELECT order_id, SUM(qty * unit_price) as sum_amt
        FROM line_items
        GROUP BY order_id
    ) sub
    WHERE o.id = sub.order_id;
END $$;
