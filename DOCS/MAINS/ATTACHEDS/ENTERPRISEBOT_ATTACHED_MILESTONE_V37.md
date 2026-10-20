# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V37.md
# Anexo H37 — Albaranes Digitales y Órdenes de Trabajo ASISTENCIA

---

**ABIERTO EN S131** (2026-10-20, PCH CASO C desde H30, decisión de
Miguel Ángel: hito nuevo H37 en vez de reconstruir el anexo V17).

## 1. Objetivo del hito

Terminar y poner en uso real el flujo de albaranes digitales de la
sección ASISTENCIA (grúas de asistencia en carretera para
aseguradoras):

1. Orden de trabajo de asistencia creada desde un presupuesto aceptado
   (H16) o directamente.
2. Una o varias unidades (grúa + operario) por servicio, cada una con
   su albarán.
3. El operario recibe el albarán prellenado por WhatsApp, lo completa
   en el móvil o la tablet y el cliente lo firma en pantalla.
4. El albarán firmado se guarda, sale en PDF y se envía al cliente.
5. El albarán tiene que poder rellenarse y firmarse sin cobertura y
   enviarse solo cuando vuelva la conexión.

Aseguradora de referencia para validar los campos: **Allianz**
(decisión de Miguel Ángel en S131).

## 2. Por qué es un hito nuevo y no H17

En `ENTERPRISEBOT_MASTER_DOCUMENT.md` el Hito 17 sigue descrito como
"Albaranes y Órdenes de Trabajo ASISTENCIA", pero el enrutador y el
anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md` contienen desde S014
"Unificación IVR + WhatsApp — Motor de Averías y Log de
Conversaciones". El diseño original de los albaranes no está en ningún
anexo: solo en los chats de S001-H17 (2026-06-02) y H17-S002
(2026-06-03). Miguel Ángel decidió en S131 abrir H37 para los albaranes
y dejar H17 como está. Todo lo de albaranes de ASISTENCIA se anota a
partir de ahora aquí.

## 3. Estado real del código al abrir el hito (revisado en S131)

### 3.1. Modelos (`budgets/models.py`)

- `WorkOrderAssistance` (~línea 1569): documento central del servicio.
  Empresa, presupuesto de origen, aseguradora, tipo de vehículo,
  operario, base, número de orden, fecha, expediente, estado,
  `is_overnight`; datos del cliente y del vehículo; recogida y
  destino; importes; bloque del parte del operario (horas de salida y
  llegada, km, horas y litros de motores A/B, notas);
  `whatsapp_notification_sent`; y los campos del PDF de Allianz:
  `provider_code`, `policy_number`, `insured_name`, `arrival_time`,
  `load_time`, `request_time`, `service_start_time`,
  `completion_time`, `location_elapsed`, `second_service`,
  `own_crane_management`, `is_accident`, `is_failed`, `is_billable`,
  `insurer_comments`, `company_observations`, `vehicle_model`,
  `vehicle_color`, `vehicle_type_label`, `vehicle_subtype_label`,
  `vehicle_weight`, `vehicle_axes`, `vehicle_tare`, `num_passengers`,
  `breakdown_description`, `breakdown_code`, `repair_on_site`,
  `pickup_type/province/country/cp`,
  `delivery_type/province/locality/country/address`, `ris_motive`,
  `driver_km`, `total_km_tirea`.
- `WorkOrderAssistanceUnit` (~2449): una por grúa/operario del
  servicio. `unit_number`, `machine`, `is_overnight`, `departure_fee`,
  `rescue_hours`, `wait_hours`, `synced_at` y la trazabilidad de
  estados con sus fechas: `PENDING` → `NOTIFIED` → `DOWNLOADED` →
  `IN_PROGRESS` → `COMPLETED` → `CLOSED_UNSIGNED` (con
  `unsigned_reason`) / `SIGNED_RECEIVED` (`signed_received_at/by`).
- `WorkOrderAssistanceSignature` (~2770): `signature_data`,
  `signer_name`, `signed_offline`, `signed_at`.
- `WorkOrderAssistanceIncidence` (~2841): cambios sobre la marcha
  (`memo`, operario, máquina, salida, horas de rescate y espera).
- `whatsapp.WhatsAppSession.pending_albaran_units` (JSON): unidades
  cuyo enlace se manda cuando el operario responde a la plantilla.

### 3.2. Vistas y URLs (`budgets/views.py` ~5142-5840, `budgets/urls.py`)

| URL (bajo `/panel/budgets/`) | Vista | Qué hace |
|---|---|---|
| `budgets/<pk>/work-order/create/` | `WorkOrderCreateFromBudgetView` | Orden desde presupuesto `ACCEPTED` (botón en `result.html`) |
| `work-orders/new/` | `WorkOrderCreateDirectView` | Orden directa |
| `work-orders/<pk>/` | `WorkOrderDetailView` | Detalle (`work_order_detail.html`) |
| `work-orders/units/<pk>/albaran/` | `WorkOrderAlbaranView` | Albarán móvil del operario con firma táctil (`albaran_operario.html`) |
| `work-orders/units/<pk>/pdf/` | `WorkOrderPdfView` | PDF con weasyprint (`albaran_pdf.html`) |
| `albaran-demo/` | `AlbaranDemoView` | Prototipo sin conexión de S001-H17 (no guarda nada; desde aquí se bajaba el APK de prueba) |

### 3.3. Aviso al operario

`whatsapp/services.py`: `send_operator_albaran_notification()` manda
la plantilla ya aprobada `chat_session_renewal` para abrir la ventana
de 24 h y guarda la unidad en `pending_albaran_units`; cuando el
operario contesta, se le manda el enlace (`albaran_link_text()`).

### 3.4. Lo que NO existe todavía

- **Uso real: ninguno.** Consulta a BD en S131 (`db_query.yml`, run
  39397870299): 0 órdenes, 0 unidades, 0 firmas, 0 incidencias. Nada
  del flujo se ha probado de principio a fin en producción.
- **Modo sin conexión en el albarán real:** solo lo tiene el prototipo.
  No hay repositorio de app Android de albaranes en la cuenta de
  GitHub (el `AlbaranApp` Kotlin de S001-H17 —paquete
  `com.miguelaetxio.albaran`, SharedPreferences, `SignaturePadView`,
  OkHttp/Retrofit, solo Android— no está en ningún repositorio visible).
- **Envío del albarán firmado al cliente:** la plantilla
  `albaran_customer_delivery` (categoría MARKETING) no existe ni en
  código ni en Twilio.
- **Campos de Allianz:** diseñados en H17, nunca cotejados contra un
  servicio real de Allianz.

## 4. Las dos opciones para la app del operario (para decidir en el punto 1)

Miguel Ángel, S131: *"no sé qué será mejor, si crear una aplicación
Android o hacerlo como hemos hecho con los fichajes [...] iniciar con
esa decisión en la siguiente sesión."*

1. **Web en el panel, como el fichaje (H24).** El albarán ya es una
   página móvil del panel; faltaría guardarla en el propio navegador
   (service worker + almacenamiento local) para rellenar y firmar sin
   cobertura y enviarla al volver la conexión. Sirve en Android y en
   iPhone, sin instalar nada ni publicar APK, y cada cambio llega con
   el despliegue normal. Límite: en iPhone el navegador puede borrar
   lo guardado si la web no se abre en semanas, y el operario tiene
   que haber abierto el albarán al menos una vez con cobertura.
2. **App nativa Android (Kotlin).** Lo más robusto sin cobertura
   (guardado propio en el dispositivo, firma nativa), pero solo
   Android, exige repositorio nuevo, compilación por GitHub Actions
   (`android-build`/`android-deploy`), instalar el APK en cada tablet
   y actualizarlo en cada cambio.

### 4.1. Decisión de Miguel Ángel (S132): app nativa Android en Kotlin

Primero eligió la web "si se puede", pero solo si podía hacerlo todo.
En la misma conversación se le explicó que una página web no puede
enviar la posición de forma continua. Solo la envía mientras está
abierta en primer plano. Con la pantalla apagada puede dejar de
hacerlo, y ningún navegador permite seguir la ubicación con la página
cerrada. Su decisión final, verbatim:

*"El hecho de que no podamos enviar la posición de continuo me hace
decantarme por Kotlin de primera. Esta aplicación tiene que ser para
que trabaje en segundo plano y abierta de principio. Como voy a ser yo
quien instalará [...] sobre todo la primera tablet, la instalaré yo
directamente y las actualizaciones las haré yo, tanto en esa como en
las demás tablets que se hagan una vez que comprobemos que funciona.
Por tanto, vamos a ir a Kotlin y las primeras pruebas las vamos a
hacer desde mi propio móvil [...] Vamos a Kotlin directamente."*

Requisitos que fijó al decidir:

- La app es solo para tablets Android. Que no funcione en iPhone no
  afecta, en sus palabras: *"da igual. No nos afecta"*.
- Trabaja en segundo plano y queda abierta desde el principio.
- Envía la posición de la tablet de forma continua. El objetivo, en
  sus palabras: *"saber en todo momento dónde está el operario, el
  vehículo, en qué carreteras, tener una situación en el mapa de los
  servicios"*.
- Miguel Ángel instala la primera tablet y hace él las
  actualizaciones de todas. Las primeras pruebas se hacen en su
  propio móvil.
- Más adelante podría hacerse también la versión web; no entra en
  este hito por ahora.

### 4.2. Aviso por WhatsApp: plantilla específica de asistencia (S132)

`send_operator_albaran_notification()` usa hoy `chat_session_renewal`,
la plantilla genérica de renovación de sesión que comparten el chat y
las circulares. El operario recibe un mensaje sin mención al servicio,
y el enlace al albarán solo le llega cuando pulsa el botón de
respuesta. Miguel Ángel, S132: *"si es una genérica para retomar o
reabrir una conversación, lo suyo es que hagamos una específica de lo
que tenemos para que el operario, cuando reciba el mensaje, sepa
exactamente a lo que se refiere."*

## 5. Hoja de Ruta para la Siguiente Sesión (S132) -- concertada con Miguel Ángel al cierre de S131

Se hace en este orden.

1. **Decidir con Miguel Ángel la forma de la app del operario.** Antes
   de tocar código, exponerle las dos opciones de la sección 4 y
   construir según la que elija. **Cierre:** la decisión anotada en
   este anexo, con sus palabras, y el punto 4 de esta hoja de ruta
   redactado según ella.
   **Hecho en S132:** Kotlin, ver 4.1.
2. **Prueba completa en producción con Allianz.** Primero, la
   plantilla específica de aviso de asistencia (ver 4.2), de categoría
   UTILITY. Lleva los datos del servicio y el enlace al albarán, y
   sustituye a `chat_session_renewal` en
   `send_operator_albaran_notification()`. Se crea por Comando S, con
   el mismo patrón que `create_machine_service_whatsapp_template`.
   Esta prueba valida el servidor con el albarán web que ya existe; la
   app Kotlin llega en el punto 4. Con un presupuesto
   real de Allianz aceptado: crear la orden desde el botón del
   resultado, una unidad con operario y grúa reales, aviso por
   WhatsApp al operario, abrir el albarán desde el enlace, rellenarlo,
   firmarlo y sacar el PDF. Corregir lo que falle por el camino y
   cotejar los campos de Allianz de la sección 3.1 con un albarán o
   parte real de Allianz que aporte Miguel Ángel. **Cierre:** consulta
   a BD con la orden, su unidad en `SIGNED_RECEIVED` con
   `notified_at`, `downloaded_at`, `completed_at` y
   `signed_received_at` rellenos, una fila en
   `budgets_workorderassistancesignature` para esa unidad, y el PDF
   abierto con los datos y la firma.
3. **Envío del albarán firmado al cliente.** Plantilla
   `albaran_customer_delivery` creada por Comando S (mismo patrón que
   `create_machine_service_whatsapp_template`) y envío al teléfono del
   cliente con el enlace o el PDF al quedar firmado. **Cierre:** la
   plantilla registrada en BD con su Content SID y, una vez aprobada
   por Meta, el envío real al teléfono de prueba que indique Miguel
   Ángel con el albarán firmado del punto 2.
4. **App nativa Android en Kotlin para las tablets (decisión del punto
   1, ver 4.1).** La app necesita:
   - Repositorio propio en flujo NewFlow Android.
   - Compilación por GitHub Actions (`android-build`/`android-deploy`).
   - Albarán rellenable y firmable sin conexión, que se envía solo al
     volver la cobertura.
   - Funcionamiento en segundo plano, abierta desde el principio, con
     envío continuo de la posición de la tablet al servidor.
   - Situación de los servicios en un mapa del panel.

   Miguel Ángel instala y actualiza la app él mismo, y las primeras
   pruebas se hacen en su propio móvil. **Cierre:** dos consultas a BD.
   - Un albarán rellenado y firmado en modo avión llega al servidor al
     recuperar la conexión, con `signed_offline=True` en su firma y
     `synced_at` relleno en la unidad.
   - Las posiciones enviadas por el móvil de Miguel Ángel llegan
     registradas con la pantalla apagada.
