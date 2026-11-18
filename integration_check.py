"""Pruebas de integracion contra PostgreSQL y el proveedor simulado."""
import os, time
from concurrent.futures import ThreadPoolExecutor
import requests
from core import connect, make_order_service, SimulatedError, BusinessError, CircuitBreaker, ExternalPaymentAdapter, CircuitOpen

def scalar(sql, args=()):
    with connect() as db: return next(iter(db.execute(sql,args).fetchone().values()))
with connect() as db:
    pid=db.execute("INSERT INTO products(name,price,stock_qty) VALUES ('Integracion',3,3) RETURNING product_id").fetchone()['product_id']
    cid=db.execute('SELECT customer_id FROM customers ORDER BY customer_id LIMIT 1').fetchone()['customer_id']
before=scalar('SELECT count(*) FROM orders')
try: make_order_service().place('Prueba',cid,pid,1,True)
except SimulatedError: pass
else: raise AssertionError('No se provoco el fallo')
assert scalar('SELECT count(*) FROM orders') == before
assert scalar('SELECT stock_qty FROM products WHERE product_id=%s',(pid,)) == 3
print('OK: ROLLBACK sin pedido parcial ni descuento')
(result, events), audit = make_order_service().place('Prueba',cid,pid,1)
assert len(events)==2 and 'Proxy:' in audit
assert scalar('SELECT stock_qty FROM products WHERE product_id=%s',(pid,)) == 2
print('OK: COMMIT, Proxy y dos observadores')
try: make_order_service().place('Prueba',cid,pid,99)
except BusinessError: pass
else: raise AssertionError('No se rechazo stock insuficiente')
print('OK: consistencia, stock insuficiente rechazado')
with connect() as db:
    one=db.execute("INSERT INTO products(name,price,stock_qty) VALUES ('Concurrencia integracion',1,1) RETURNING product_id").fetchone()['product_id']
def attempt(_):
    try: make_order_service().place('Prueba',cid,one,1); return 'OK'
    except BusinessError: return 'RECHAZADO'
with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(attempt,range(2)))
assert sorted(results)==['OK','RECHAZADO']
assert scalar('SELECT stock_qty FROM products WHERE product_id=%s',(one,)) == 0
assert scalar('SELECT count(*) FROM order_items WHERE product_id=%s',(one,)) == 1
print('OK: concurrencia', results)
url=os.environ['EXTERNAL_URL']
requests.post(url+'/control',json={'failing':True},timeout=3).raise_for_status()
b=CircuitBreaker(ExternalPaymentAdapter(url),recovery_seconds=1)
for i in range(3):
    try: b.call('10','demo')
    except BusinessError: pass
assert b.state=='OPEN'
try: b.call('10','demo')
except CircuitOpen: pass
else: raise AssertionError('La llamada no fue bloqueada')
requests.post(url+'/control',json={'failing':False},timeout=3).raise_for_status()
time.sleep(1.1)
assert b.call('10','demo')['value']=='10' and b.state=='CLOSED'
print('OK: Adapter y circuito CLOSED -> OPEN -> HALF-OPEN -> CLOSED')
