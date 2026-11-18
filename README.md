# Sample Store: consistencia transaccional

Aplicacion educativa en Python, Streamlit y PostgreSQL 16 para el taller de Aplicaciones Distribuidas. La interfaz funciona en http://localhost:8501. El proveedor externo es simulado y no cobra dinero.

## Requisitos e inicio en Windows

Instale e inicie Docker Desktop con Docker Compose. Copie `.env.example` a `.env` y reemplace el valor por una clave local elegida por usted. No publique `.env`.

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up --build -d
```

Espere a que la base este lista y abra http://localhost:8501. Para detener: `docker compose down`. El volumen de PostgreSQL conserva los datos. Las variables son `POSTGRES_PASSWORD` en `.env`, y `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` y `EXTERNAL_URL` para la aplicacion (Compose las configura). No hay autenticacion real; el nombre solicitado por el Proxy es demostrativo.

## Base de datos

Se adaptan las cuatro tablas del esquema [Sample Store](https://github.com/akramsaleh12/PostgreSQL-DB-Streamlit-App): customers, products, orders y order_items. `sql/00_esquema_original.sql` conserva el esquema original compartido; `sql/01_schema.sql` contiene la version adaptada y datos iniciales (cuatro clientes, ocho productos, dos pedidos y tres detalles). Agrega comprobaciones de cantidades, precios y stock, eliminacion logica y fecha del pedido. Docker ejecuta el script solo al crear un volumen vacio.

## Pruebas

- Productos: registre, consulte, edite y desactive un producto.
- Operacion normal: en Pedidos seleccione cliente, producto y cantidad; confirme y observe el pedido, stock, Proxy y los dos observadores.
- Atomicidad: marque el error simulado antes de confirmar. Compare pedidos y existencias antes y despues; el cambio se revierte.
- Consistencia: intente pedir mas unidades de las disponibles. El pedido se rechaza; las restricciones SQL impiden stock negativo, cantidad no positiva y referencias invalidas.
- Dos clientes: abra http://localhost:8501 en dos pestanas. En ambas elija Dos clientes. En la primera pulse Crear producto con 1 unidad y anote el numero. Actualice la segunda pestana; seleccione el mismo numero en ambas y dos clientes distintos. Pulse Comprar la ultima unidad en ambas con la menor separacion posible. Cada pestana muestra su resultado; solo una compra puede confirmarse.
- Aislamiento automatizado: en Pruebas ACID pulse la prueba concurrente. Se crea un producto con una unidad, dos conexiones independientes compiten y se muestran ambos resultados y el stock final. `SELECT FOR UPDATE` mantiene el bloqueo hasta confirmar o revertir.
- Durabilidad: confirme un pedido, ejecute `docker compose restart`, vuelva a consultar Pedidos y Productos.
- Circuit Breaker: en Servicio externo haga fallar el proveedor y pulse tres veces el pago simulado: CLOSED pasa a OPEN. Otra llamada inmediata se bloquea. Recupere el proveedor, espere 10 segundos y pruebe: OPEN pasa por HALF-OPEN y cierra al tener exito. Para la rama de fallo, mantenga el proveedor fallando, espere 10 segundos y pulse de nuevo: se muestra OPEN → HALF-OPEN → OPEN. Despues recupere el proveedor, espere y repita para observar CLOSED.

El Circuit Breaker vive en la sesion de Streamlit y se reinicia al reiniciar la aplicacion; no coordina otras sesiones. Los observadores reaccionan despues del COMMIT y muestran mensajes en pantalla; no son una cola durable. El pago simulado se prueba de forma independiente y no afecta al pedido.

## Respaldo y restauracion

Generar el respaldo despues de la demostracion:

```powershell
docker compose exec -T db pg_dump -U sample_user -d sample_store -Fc -f /tmp/BD_RodriguezBruce.backup
docker compose cp db:/tmp/BD_RodriguezBruce.backup ./BD_RodriguezBruce.backup
```

Para verificarlo sin alterar la base principal, cree una base temporal y restaure alli:

```powershell
docker compose cp ./BD_RodriguezBruce.backup db:/tmp/restaurar.backup
docker compose exec -T db createdb -U sample_user prueba_restauracion
docker compose exec -T db pg_restore -U sample_user -d prueba_restauracion /tmp/restaurar.backup
docker compose exec -T db psql -U sample_user -d prueba_restauracion -c "SELECT count(*) FROM orders;"
```

No publique `.env`, dependencias descargadas, cache ni datos sensibles. Incluya el backup requerido en el ZIP de entrega, sin incluirlo en Git si contiene datos privados.

## Arquitectura y SOLID

`app.py` presenta formularios; `core.py` define contratos, logica, repositorio PostgreSQL, Proxy, observadores, Adapter y Circuit Breaker; `external_service.py` simula el proveedor. Responsabilidad unica separa componentes; el contrato Observer admite nuevas reacciones sin modificar el servicio (abierto/cerrado); AuditObserver y NotificationObserver se sustituyen por el mismo contrato (Liskov); los contratos OrderRepository, Observer y PaymentGateway tienen funciones acotadas (segregacion); OrderService depende de OrderRepository (inversion de dependencias). El Proxy recibe usuario y delega; el Adapter transforma `pay` en `executeTransaction`.

## Codigo visible y pruebas automatizadas

La seccion «Codigo del proyecto» muestra fragmentos reales de la transaccion y patrones. Para ejecutar la verificacion de integracion (crea registros de prueba):

```powershell
docker compose exec -T app python integration_check.py
```

Las capturas de demostracion y el informe se generan por separado. Para construir el proyecto desde el esquema inicial, use un volumen PostgreSQL nuevo; el script de inicializacion se ejecuta solo la primera vez.

El SQL original se incluye como referencia y no se ejecuta automaticamente. Compose solo monta `01_schema.sql` para inicializar una base nueva; el backup incluye los datos reales utilizados durante las pruebas. La eliminacion es logica para conservar pedidos historicos.
