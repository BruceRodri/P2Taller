import os
import inspect
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

from core import (CircuitBreaker, ExternalPaymentAdapter, PostgresOrders, OrderProxy,
                  OrderService, AuditObserver, NotificationObserver, SimulatedError,
                  connect, make_order_service)

st.set_page_config(page_title='Sample Store', page_icon='🛍️', layout='wide', initial_sidebar_state='expanded')
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
html, body, [class*="css"], [data-testid="stApp"] {font-family: 'DM Sans', sans-serif;}
[data-testid="stAppViewContainer"] {background: #f6f7fb;}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stMainBlockContainer"] {max-width: 1250px; padding-top: 2.3rem; padding-bottom: 4rem;}
[data-testid="stSidebar"] {background: #111b34; border: 0;}
[data-testid="stSidebar"] * {color: #e8edff;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {color: #aab7d4;}
[data-testid="stSidebar"] [role="radiogroup"] {gap: .35rem;}
[data-testid="stSidebar"] [role="radiogroup"] label {padding: .65rem .8rem; border-radius: 10px;}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {background: #29385c;}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding: 1.4rem .8rem;}
h1, h2, h3 {font-family: 'Manrope', sans-serif; letter-spacing: -.035em; color: #15203a;}
h1 {font-size: 2.15rem !important; line-height: 1.15 !important;}
h2 {font-size: 1.45rem !important;}
h3 {font-size: 1.05rem !important; letter-spacing: -.015em;}
.eyebrow {font-size: .72rem; font-weight: 800; letter-spacing: .14em; color: #635bdb; text-transform: uppercase; margin-bottom: .45rem;}
.page-description {color: #69758e; font-size: .98rem; margin-top: -.3rem; margin-bottom: 1.6rem; max-width: 720px;}
.brand {font-family: 'Manrope', sans-serif; color: white; font-size: 1.25rem; font-weight: 800; letter-spacing: -.04em; margin: .2rem 0 0;}
.brand-icon {display:inline-flex; justify-content:center; align-items:center; background: #7268f2; color:white; width: 34px; height:34px; border-radius: 11px; margin-right: .55rem;}
.brand-subtitle {font-size: .75rem; color: #9cabc9; margin: .45rem 0 2rem 2.65rem;}
.sidebar-label {font-size: .66rem; color: #8697bb; letter-spacing: .14em; font-weight: 800; margin: 1.6rem 0 .4rem .8rem;}
.sidebar-footer {margin: 2rem .8rem 0; padding-top: 1.2rem; border-top: 1px solid #34415e; color: #aab7d4; font-size:.75rem; line-height:1.6;}
[data-testid="stMetric"] {background: #fff; border: 1px solid #e8ebf3; border-radius: 16px; padding: 1.05rem 1.2rem; box-shadow: 0 4px 18px #27335a08;}
[data-testid="stMetricLabel"] {color: #6d7990; font-weight: 600;}
[data-testid="stMetricValue"] {font-family: 'Manrope', sans-serif; font-weight: 800; color: #1c2845;}
[data-testid="stVerticalBlockBorderWrapper"] > div {background: #fff; border-color: #e8ebf3; border-radius: 16px; box-shadow: 0 4px 18px #27335a08;}
div[data-testid="stForm"] {border: 1px solid #e8ebf3; border-radius: 16px; background: #fff; padding: 1.2rem;}
.stButton > button, [data-testid="stFormSubmitButton"] > button {border-radius: 10px; font-weight: 700; min-height: 2.7rem;}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primary"] {background: #554ce3; border-color: #554ce3; box-shadow: 0 4px 12px #554ce329;}
.stButton > button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {background: #4338ca; border-color: #4338ca; color: white;}
[data-testid="stTabs"] [role="tablist"] {gap: 1.3rem; border-bottom: 1px solid #e2e7f0;}
[data-testid="stTabs"] button[role="tab"] {font-weight: 700; color: #73809a; padding: .8rem .2rem;}
[data-testid="stTabs"] button[aria-selected="true"] {color: #554ce3;}
[data-testid="stCaptionContainer"] {color: #7b879e;}
.hero-note {border-radius: 16px; background: #eeedff; color: #403ba0; padding: 1rem 1.2rem; font-size: .9rem; line-height: 1.5;}
.status-pill {display:inline-block; border-radius:99px; padding:.35rem .7rem; font-size:.7rem; font-weight:800; letter-spacing:.04em; background:#eef2ff; color:#5147ce;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="brand"><span class="brand-icon">S</span>sample store</div><div class="brand-subtitle">PANEL DE GESTIÓN</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-label">ESPACIO DE TRABAJO</div>', unsafe_allow_html=True)
    page = st.radio('Navegación', ['Productos', 'Pedidos', 'Pruebas ACID', 'Servicio externo', 'Código del proyecto'], label_visibility='collapsed')
    st.markdown('<div class="sidebar-footer">APLICACIONES DISTRIBUIDAS<br><strong>Taller de consistencia</strong><br>Python · PostgreSQL</div>', unsafe_allow_html=True)

url = os.getenv('EXTERNAL_URL', 'http://localhost:8080')
if 'breaker' not in st.session_state:
    st.session_state.breaker = CircuitBreaker(ExternalPaymentAdapter(url))


def query(sql, params=()):
    with connect() as db:
        return db.execute(sql, params).fetchall()


def heading(kicker, title, description):
    st.markdown(f'<div class="eyebrow">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="page-description">{description}</div>', unsafe_allow_html=True)


def show_error(exc):
    st.error(f'{type(exc).__name__}: {exc}')


def product_label(product):
    return f"#{product['product_id']} · {product['name']}"


try:
    if page == 'Productos':
        heading('Inventario / Productos', 'Tu inventario, en orden', 'Consulta tus productos y mantén actualizados sus precios y existencias desde un solo lugar.')
        if 'product_notice' in st.session_state:
            st.success(st.session_state.pop('product_notice'))
        rows = query('SELECT * FROM products ORDER BY product_id')
        active_rows = [row for row in rows if row['active']]
        a, b, c = st.columns(3)
        a.metric('Productos activos', len(active_rows))
        b.metric('Unidades disponibles', sum(row['stock_qty'] for row in active_rows))
        c.metric('Productos sin stock', sum(row['stock_qty'] == 0 for row in active_rows))
        st.write('')
        catalog, create, edit = st.tabs(['Inventario', 'Agregar producto', 'Editar producto'])
        with catalog:
            st.subheader('Catálogo de productos')
            st.caption('Un vistazo a los productos registrados. Los productos inactivos no aparecen al crear pedidos.')
            if rows:
                st.dataframe(rows, hide_index=True, width='stretch', column_config={
                    'product_id': st.column_config.NumberColumn('ID', width='small'),
                    'name': st.column_config.TextColumn('Producto', width='medium'),
                    'description': st.column_config.TextColumn('Descripción', width='large'),
                    'price': st.column_config.NumberColumn('Precio', format='$ %.2f'),
                    'stock_qty': st.column_config.NumberColumn('Existencias'),
                    'active': st.column_config.CheckboxColumn('Activo')})
            else:
                st.info('Aún no hay productos. Agrega el primero en la pestaña superior.')
        with create:
            st.subheader('Nuevo producto')
            st.caption('Completa los datos para incorporarlo al catálogo.')
            with st.form('create', clear_on_submit=True):
                name = st.text_input('Nombre del producto', placeholder='Ej. Audífonos inalámbricos')
                description = st.text_input('Descripción', placeholder='Una descripción breve')
                col1, col2 = st.columns(2)
                price = col1.number_input('Precio de venta ($)', min_value=0.0, step=0.5)
                stock = col2.number_input('Existencias iniciales', min_value=0, step=1)
                if st.form_submit_button('Agregar al inventario', type='primary'):
                    if not name.strip():
                        st.error('Escribe el nombre del producto.')
                    else:
                        with connect() as db:
                            db.execute('INSERT INTO products(name,description,price,stock_qty) VALUES (%s,%s,%s,%s)', (name.strip(), description, price, stock))
                        st.session_state.product_notice = 'Producto agregado correctamente.'
                        st.rerun()
        with edit:
            st.subheader('Actualizar producto')
            st.caption('Edita sus datos o desactívalo para retirarlo de nuevos pedidos.')
            if rows:
                by_id = {row['product_id']: row for row in rows}
                selected_id = st.selectbox('Selecciona un producto', list(by_id), format_func=lambda pid: product_label(by_id[pid]))
                selected = by_id[selected_id]
                with st.form('edit'):
                    name2 = st.text_input('Nombre', selected['name'])
                    desc2 = st.text_input('Descripción', selected['description'] or '')
                    col1, col2 = st.columns(2)
                    price2 = col1.number_input('Precio ($)', min_value=0.0, value=float(selected['price']))
                    stock2 = col2.number_input('Existencias', min_value=0, value=selected['stock_qty'])
                    active = st.checkbox('Producto activo', value=selected['active'])
                    if st.form_submit_button('Guardar cambios', type='primary'):
                        if not name2.strip():
                            st.error('Escribe el nombre del producto.')
                        else:
                            with connect() as db:
                                db.execute('UPDATE products SET name=%s,description=%s,price=%s,stock_qty=%s,active=%s WHERE product_id=%s', (name2.strip(), desc2, price2, stock2, active, selected_id))
                            st.session_state.product_notice = 'Cambios guardados correctamente.'
                            st.rerun()
                st.caption('Para realizar una eliminación lógica, desmarca «Producto activo» y guarda los cambios.')
            else:
                st.info('Primero registra un producto.')

    elif page == 'Pedidos':
        heading('Operaciones / Pedidos', 'Crear un pedido', 'Selecciona un cliente y un producto. Al confirmar, el inventario se actualiza de forma segura.')
        customers = query('SELECT * FROM customers ORDER BY customer_id')
        products = query('SELECT * FROM products WHERE active ORDER BY product_id')
        left, right = st.columns([1.3, 0.8], gap='large')
        with left:
            with st.container(border=True):
                st.subheader('Datos del pedido')
                if not customers or not products:
                    st.warning('Se requiere al menos un cliente y un producto activo.')
                else:
                    c = st.selectbox('Cliente', customers, format_func=lambda x: f"{x['first_name']} {x['last_name']}")
                    p = st.selectbox('Producto', products, format_func=lambda x: f"{x['name']} · {x['stock_qty']} disponibles · ${x['price']}")
                    qty = st.number_input('Cantidad', min_value=1, step=1)
                    user = st.text_input('Responsable de la operación', 'Bruce')
                    with st.expander('Opciones de demostración'):
                        fail = st.checkbox('Provocar un error antes de confirmar (ROLLBACK)')
                        st.caption('Permite comprobar que el pedido y el descuento se revierten juntos.')
                    if st.button('Confirmar pedido', type='primary', width='stretch'):
                        before = query('SELECT (SELECT count(*) FROM orders) AS pedidos, (SELECT stock_qty FROM products WHERE product_id=%s) AS stock', (p['product_id'],))[0]
                        try:
                            (order, events), proxy = make_order_service().place(user, c['customer_id'], p['product_id'], qty, fail)
                            st.success(f"Pedido #{order['order_id']} confirmado · Total ${order['total']}")
                            st.caption(proxy)
                            for event in events:
                                st.info(event)
                        except SimulatedError as exc:
                            after = query('SELECT (SELECT count(*) FROM orders) AS pedidos, (SELECT stock_qty FROM products WHERE product_id=%s) AS stock', (p['product_id'],))[0]
                            st.error('ROLLBACK ejecutado: el error simulado revirtió la operación.')
                            st.write('**Comparación de datos antes y después del fallo**')
                            st.dataframe([{'Momento': 'Antes', 'Pedidos': before['pedidos'], 'Existencias': before['stock']}, {'Momento': 'Después', 'Pedidos': after['pedidos'], 'Existencias': after['stock']}], hide_index=True, width='stretch')
                        except Exception as exc:
                            show_error(exc)
        with right:
            st.markdown('<div class="hero-note"><strong>Una operación segura</strong><br>El pedido y la actualización del inventario forman parte de una sola transacción.</div>', unsafe_allow_html=True)
            st.write('')
            st.markdown('**Así funciona**')
            st.write('01 · Elige un cliente y un producto')
            st.write('02 · Verifica la cantidad disponible')
            st.write('03 · Confirma el pedido')
        st.write('')
        st.subheader('Historial de pedidos')
        orders = query('SELECT o.order_id, c.first_name, c.last_name, o.status, o.created_at, p.name, i.quantity, i.unit_price FROM orders o JOIN customers c USING(customer_id) JOIN order_items i USING(order_id) JOIN products p USING(product_id) ORDER BY o.order_id DESC')
        if orders:
            st.dataframe(orders, hide_index=True, width='stretch', column_config={'order_id': 'Pedido', 'first_name': 'Nombre', 'last_name': 'Apellido', 'status': 'Estado', 'created_at': 'Fecha', 'name': 'Producto', 'quantity': 'Cantidad', 'unit_price': st.column_config.NumberColumn('Precio unitario', format='$ %.2f')})
        else:
            st.info('Aún no hay pedidos registrados.')

    elif page == 'Pruebas ACID':
        heading('Laboratorio / Consistencia', 'Prueba de concurrencia', 'Observa qué ocurre cuando dos clientes intentan comprar la última unidad al mismo tiempo.')
        a, b, c = st.columns(3)
        a.metric('Clientes simultáneos', '2')
        b.metric('Unidades iniciales', '1')
        c.metric('Resultado esperado', '1 compra')
        st.write('')
        with st.container(border=True):
            st.subheader('El reto de la última unidad')
            st.write('Se crea un producto de prueba con una unidad disponible. Dos conexiones independientes intentan comprarla a la vez.')
            if st.button('Ejecutar prueba concurrente', type='primary'):
                with connect() as db:
                    pid = db.execute("INSERT INTO products(name,description,price,stock_qty) VALUES ('Prueba concurrencia','Creado para el experimento',1,1) RETURNING product_id").fetchone()['product_id']
                    ids = [x['customer_id'] for x in db.execute('SELECT customer_id FROM customers ORDER BY customer_id LIMIT 2').fetchall()]
                def attempt(cid):
                    try:
                        result, _ = make_order_service().place(f'Cliente {cid}', cid, pid, 1)
                        return True, f"Cliente {cid}: pedido #{result[0]['order_id']} confirmado"
                    except Exception as exc:
                        return False, f'Cliente {cid}: {exc}'
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(attempt, ids))
                st.markdown('**Resultados de la prueba**')
                for success, message in results:
                    (st.success if success else st.warning)(message)
                stock_final = query('SELECT stock_qty FROM products WHERE product_id=%s', (pid,))[0]['stock_qty']
                details = query('SELECT order_id, quantity FROM order_items WHERE product_id=%s', (pid,))
                st.metric('Existencias finales', stock_final)
                st.caption(f'Producto de prueba #{pid} · Pedidos confirmados: {len(details)}')
        st.info('PostgreSQL bloquea la fila del producto durante la transacción para mantener el inventario consistente.')
        st.caption('Para demostrar atomicidad, activa el error simulado en Pedidos. Para durabilidad, confirma un pedido, reinicia los contenedores y vuelve a consultarlo.')

    elif page == 'Código del proyecto':
        heading('Proyecto / Código', 'Así está construido', 'Fragmentos reales del proyecto para estudiar la transacción y los patrones de diseño.')
        examples = {
            'Transacción, COMMIT y ROLLBACK': (PostgresOrders.create, 'El contexto de conexión confirma si termina sin errores y revierte cuando ocurre una excepción.'),
            'Proxy': (OrderProxy, 'El Proxy verifica el responsable e intercepta la operación antes de delegar al servicio.'),
            'Observer y servicio': (OrderService, 'El servicio notifica a los observadores después de confirmar la transacción.'),
            'Observadores': (AuditObserver, 'Auditoría y notificación implementan el mismo contrato.'),
            'Adapter': (ExternalPaymentAdapter, 'El adaptador convierte pay al protocolo del proveedor simulado.'),
            'Circuit Breaker': (CircuitBreaker, 'El circuito detiene las llamadas y prueba la recuperación después del tiempo de espera.'),
        }
        choice = st.selectbox('Selecciona un componente', list(examples))
        component, explanation = examples[choice]
        st.caption(explanation)
        code = inspect.getsource(component)
        if choice == 'Observadores':
            code += '\n' + inspect.getsource(NotificationObserver)
        st.code(code, language='python', line_numbers=True)
    else:
        heading('Laboratorio / Servicio externo', 'Circuit Breaker', 'Simula la caída de un proveedor y observa cómo la aplicación controla los intentos de conexión.')
        breaker = st.session_state.breaker
        a, b, c = st.columns(3)
        state_metric = a.empty()
        failure_metric = b.empty()
        state_metric.metric('Estado del circuito', breaker.state)
        failure_metric.metric('Fallos consecutivos', breaker.failures)
        c.metric('Tiempo de espera', f'{breaker.recovery_seconds} s')
        st.write('')
        left, right = st.columns([1, 1], gap='large')
        with left:
            with st.container(border=True):
                st.subheader('Control del proveedor')
                st.write('Activa o desactiva los fallos del servicio simulado para probar su comportamiento.')
                if st.button('Simular fallo del proveedor', width='stretch'):
                    requests.post(url + '/control', json={'failing': True}, timeout=3).raise_for_status()
                    st.warning('El proveedor está en modo fallo.')
                if st.button('Recuperar proveedor', width='stretch'):
                    requests.post(url + '/control', json={'failing': False}, timeout=3).raise_for_status()
                    st.success('El proveedor se ha recuperado.')
        with right:
            with st.container(border=True):
                st.subheader('Enviar solicitud de prueba')
                st.write('El Adapter transforma la solicitud al formato del proveedor externo.')
                if st.button('Probar pago simulado', type='primary', width='stretch'):
                    before = breaker.state
                    try:
                        result = breaker.call('10.00', 'demo')
                        if before == 'OPEN':
                            st.info('OPEN → HALF-OPEN: se permitió una llamada de prueba.')
                        st.success(f"{before} → {breaker.state} · Referencia: {result['reference']}")
                    except Exception as exc:
                        if before == 'OPEN' and breaker.state == 'OPEN' and time.monotonic() - breaker.opened_at < breaker.recovery_seconds:
                            st.warning('Llamada bloqueada o prueba fallida; circuito OPEN.')
                        show_error(exc)
                    state_metric.metric('Estado del circuito', breaker.state)
                    failure_metric.metric('Fallos consecutivos', breaker.failures)
                    st.write(f'Estado actual: **{breaker.state}** · Fallos: **{breaker.failures}**')
        st.caption('El servicio es simulado: no se realiza ningún pago real. Tras tres fallos el circuito se abre; después de 10 segundos permite una llamada de prueba.')
except Exception as exc:
    show_error(exc)
