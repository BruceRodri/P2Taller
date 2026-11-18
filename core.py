"""Contratos y componentes intercambiables del dominio Sample Store."""
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
import psycopg
from psycopg.rows import dict_row
import requests

class BusinessError(Exception): pass
class SimulatedError(Exception): pass
class CircuitOpen(Exception): pass

def connect():
    return psycopg.connect(host=os.environ.get('DB_HOST', 'localhost'), dbname=os.environ.get('DB_NAME','sample_store'), user=os.environ.get('DB_USER','sample_user'), password=os.environ['DB_PASSWORD'], row_factory=dict_row)

# Interfaces pequenas: repositorio de pedidos y observadores (I y D de SOLID).
class OrderRepository(ABC):
    @abstractmethod
    def create(self, customer_id, product_id, quantity, fail=False): pass

class PostgresOrders(OrderRepository):
    def create(self, customer_id, product_id, quantity, fail=False):
        if quantity <= 0:
            raise BusinessError('La cantidad debe ser mayor que cero.')
        # Se confirma al salir normalmente; una excepcion causa ROLLBACK.
        with connect() as db:
            product = db.execute(
                'SELECT product_id, name, price, stock_qty FROM products '
                'WHERE product_id=%s AND active FOR UPDATE', (product_id,)
            ).fetchone()
            if not product:
                raise BusinessError('El producto no existe o esta inactivo.')
            if product['stock_qty'] < quantity:
                raise BusinessError('Existencias insuficientes.')
            customer = db.execute(
                'SELECT customer_id FROM customers WHERE customer_id=%s',
                (customer_id,)
            ).fetchone()
            if not customer:
                raise BusinessError('El cliente no existe.')
            order = db.execute(
                "INSERT INTO orders(customer_id,status) "
                "VALUES (%s,'completed') RETURNING order_id", (customer_id,)
            ).fetchone()['order_id']
            db.execute(
                'INSERT INTO order_items(order_id,product_id,quantity,unit_price) '
                'VALUES (%s,%s,%s,%s)',
                (order, product_id, quantity, product['price'])
            )
            db.execute(
                'UPDATE products SET stock_qty=stock_qty-%s WHERE product_id=%s',
                (quantity, product_id)
            )
            if fail:
                raise SimulatedError('Error intencional: transaccion revertida.')
        return {'order_id': order, 'product': product['name'],
                'quantity': quantity, 'total': str(product['price'] * quantity)}

class Observer(ABC):
    @abstractmethod
    def update(self, order): pass
class AuditObserver(Observer):
    def update(self, order): return f"Auditoria: pedido {order['order_id']} confirmado"
class NotificationObserver(Observer):
    def update(self, order): return f"Notificacion: pedido {order['order_id']} confirmado"

class OrderService:
    def __init__(self, repository: OrderRepository, observers):
        self.repository, self.observers = repository, observers
    def place(self, customer_id, product_id, quantity, fail=False):
        order = self.repository.create(customer_id, product_id, quantity, fail)
        # Las reacciones ocurren despues del COMMIT, no dentro de la transaccion.
        return order, [observer.update(order) for observer in self.observers]

class OrderProxy:
    def __init__(self, service): self.service = service
    def place(self, user, customer_id, product_id, quantity, fail=False):
        if not user.strip(): raise BusinessError('Indique quien realiza la operacion.')
        result = self.service.place(customer_id, product_id, quantity, fail)
        return result, f'Proxy: {user} ejecuto el pedido a las {time.strftime("%Y-%m-%d %H:%M:%S")}'

def make_order_service(): return OrderProxy(OrderService(PostgresOrders(), [AuditObserver(), NotificationObserver()]))

class PaymentGateway(ABC):
    @abstractmethod
    def pay(self, amount, code): pass
class ExternalPaymentAdapter(PaymentGateway):
    def __init__(self, url): self.url = url.rstrip('/')
    def pay(self, amount, code):
        response = requests.post(self.url + '/executeTransaction', json={'value': str(amount), 'code': code}, timeout=3)
        response.raise_for_status()
        return response.json()

@dataclass
class CircuitBreaker:
    gateway: PaymentGateway
    threshold: int = 3
    recovery_seconds: int = 10
    failures: int = 0
    state: str = 'CLOSED'
    opened_at: float = 0
    def call(self, amount, code):
        if self.state == 'OPEN':
            if time.monotonic() - self.opened_at < self.recovery_seconds:
                raise CircuitOpen('OPEN: llamada bloqueada sin contactar al proveedor.')
            self.state = 'HALF-OPEN'
        try:
            result = self.gateway.pay(amount, code)
        except (requests.RequestException, ValueError) as exc:
            self.failures += 1
            if self.state == 'HALF-OPEN' or self.failures >= self.threshold:
                self.state, self.opened_at = 'OPEN', time.monotonic()
            raise BusinessError(f'Proveedor no disponible: {exc}') from exc
        self.failures, self.state = 0, 'CLOSED'
        return result
