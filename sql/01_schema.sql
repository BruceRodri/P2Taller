-- Adaptado del esquema publicado en Sample Store. Se agregan restricciones y eliminacion logica.
CREATE TABLE customers (
 customer_id SERIAL PRIMARY KEY, first_name VARCHAR(100) NOT NULL,
 last_name VARCHAR(100) NOT NULL, email VARCHAR(255)
);
CREATE TABLE products (
 product_id SERIAL PRIMARY KEY, name VARCHAR(200) NOT NULL,
 description TEXT, price NUMERIC(10,2) NOT NULL CHECK (price >= 0),
 stock_qty INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
 active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE orders (
 order_id SERIAL PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
 status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','shipped','completed','cancelled')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE order_items (
 order_item_id SERIAL PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(order_id),
 product_id INTEGER NOT NULL REFERENCES products(product_id),
 quantity INTEGER NOT NULL CHECK (quantity > 0), unit_price NUMERIC(10,2) NOT NULL CHECK (unit_price >= 0)
);
INSERT INTO customers(first_name,last_name,email) VALUES ('Ana','Torres','ana@example.com'),('Luis','Perez','luis@example.com');
INSERT INTO products(name,description,price,stock_qty) VALUES ('Teclado','Teclado USB',20.00,10),('Raton','Raton inalambrico',15.00,5),('Producto para concurrencia','Una unidad disponible',8.00,1);
