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

### 4.3. Sección "Servicios" del panel (S132)

Miguel Ángel, S132, verbatim (dictado, solo limpiado de muletillas):
*"vamos a crear una entrada nueva. Tenemos una que es la que enlaza con
una prueba que hicimos, el tema de Albarán. Vamos a crear una o
modificar esa [...] que se va a llamar ahora servicios. En servicios
vamos a utilizar el mismo formato que estamos utilizando en
documentación. Esos servicios de asistencia [...] los va a poder
visionar supervisores y administradores. Supervisores de asistencia.
Vamos a crear el supervisor de asistencia y esa página la van a poder
ver única y exclusivamente administradores y supervisores de
asistencia. Vamos a navegar con el tema de pestañas. Y ahí tendremos
que tener la gestión de los albaranes, porque los albaranes no van a
entrar a partir de los presupuestos aceptados, que podrán hacerlo,
sino van a entrar a través de una imagen sacada del propio TIREA. Es
decir, el supervisor sacará una foto del albarán, la sube y a partir
de ahí es cuando empezamos a generar el albarán. Tenemos que tener una
parte de mapa para controlar los servicios que hay, los conductores
que están asignados, los camiones, los vehículos que hay libres,
furgonetas, remolcadores, en fin, los vehículos que están asignados a
la asistencia, bases, etcétera. Lo que es el control gráfico del mapa
con los servicios y vehículos y operarios. Y luego tendremos la parte
para gestionar en ese mismo mapa una parte, tal como hicimos también
con el laboratorio de análisis, con ampliar el mapa o ampliar [...] la
pestaña de control. Es que no sé cómo hacerlo. Como no sé todavía
tampoco todas las cosas que hay que controlar. A mí Pepe me pasó un
PDF."*

Lo que fija:

- La entrada de menú "Albarán (demo)" (`budgets:albaran_demo`, sección
  de Asistencia del menú) pasa a llamarse **Servicios**.
- Rol nuevo **Supervisor de asistencia**. La página la ven única y
  exclusivamente los administradores y los supervisores de asistencia.
- Mismo formato que Documentación, con navegación por pestañas.
- **Gestión de albaranes**: la vía principal de entrada es una foto del
  albarán de TIREA que sube el supervisor; desde ella se genera el
  albarán. Desde un presupuesto aceptado se podrá seguir haciendo. Ya
  decidido en H17-S002 (2026-06-03): fuente de entrada única, foto JPG
  del albarán TIREA procesada por Gemini Vision.
- **Mapa**: servicios en curso, conductores asignados, vehículos de
  asistencia (camiones, furgonetas, remolcadores...) libres y
  asignados, y bases.
- **Control**: una parte de gestión sobre el mismo mapa, ampliable
  como en el Laboratorio de Análisis. Su contenido está sin definir:
  depende del PDF que Pepe pasó a Miguel Ángel.

### 4.4. Dossier de Pepe: especificación funcional de la aplicación (S132)

Aportado por Miguel Ángel en S132:
`DOCS_ATTACHED_2_ANNEX_V37/Dossier_Completo_App_Asistencia_Camiones_Gruas_Alvarez.pdf`
(37 páginas, 35 apartados). Es el PDF que "Pepe me pasó" (4.3) y define
la parte de control. Lo esencial, resumido:

- **Idea central:** un panel de tráfico visual para la oficina, abierto
  todo el día, que muestra de un vistazo qué conductores y máquinas
  están libres y qué servicios están abiertos. No una tabla.
- **Pantalla principal:** tres columnas de tarjetas grandes con color:
  conductores (libres y ocupados), máquinas (libres, ocupadas,
  regresando, en taller) y albaranes abiertos. Arriba, botones de nuevo
  servicio, buscar albarán, mapa y estadísticas. Filtro por categoría de
  máquina; orden por disponibilidad, hora o urgencia.
- **Máquinas por nombre interno** (B30, B35, A30, A39, X02), con foto,
  matrícula, categoría (ligera, pesada, rescate, plataforma, furgón
  taller), estado, km y próximo mantenimiento.
- **Conductores** como tarjetas con foto, teléfono, permisos por tipo de
  máquina y estado (libre, asignado, en servicio, regresando, descanso,
  baja, no disponible).
- **Asignación arrastrando** la tarjeta del conductor y la de la máquina
  al albarán. No se puede asignar algo ocupado ni una máquina en taller.
- **Estados y colores del albarán:** rojo creado o pendiente; amarillo
  enviado o en servicio; verde terminado, firmado y regresando a base;
  gris cerrado; azul programado; naranja incidencia.
- **Flujo:** entra el aviso, la oficina crea el albarán (rojo), asigna
  máquina y conductor, pulsa enviar (amarillo), el conductor hace el
  servicio y recoge la firma (verde, conductor y máquina "regresando"),
  y en base mete los km finales y los litros repostados y cierra (gris,
  conductor y máquina libres de nuevo).
- **Dos hojas del mismo albarán:** la del conductor (operativa, sin
  precios ni notas) y la interna de oficina (notas privadas para
  facturación).
- **Reglas:** no se envía sin conductor y máquina; no se cierra sin
  firma o motivo de no firma; no se cierra en base sin km finales ni
  sin indicar si repostó; cada cambio de estado guarda hora y usuario;
  los albaranes no se borran, se corrigen con auditoría.
- **Además:** control de km y gasoil con consumo por máquina, avisos de
  mantenimiento y de documentación, historial y buscador, exportaciones,
  alertas (servicio sin enviar, sin km de salida, demasiado tiempo en
  amarillo, sin cerrar en base...), estadísticas y facturación.
- **Fases que propone:** 1) datos de máquinas, conductores y servicios;
  2) panel de tráfico y asignación; 3) vista del conductor y firma;
  4) cierre en base con km y gasoil; 5) historial, buscador y PDF;
  6) mantenimiento y avisos; 7) estadísticas y facturación.

Ya decidido antes de recibirlo y que el dossier deja abierto: app nativa
Android en tablets (4.1), entrada del albarán desde foto de TIREA
(4.3), GPS continuo (4.1).

## 5. COMPLETADAS EN S132 (20/10/2026, PEE PC; H37 -- puntos 1, 2 y 3 de la hoja de ruta y prueba completa del albarán en producción)

### 5.1. Punto 1 -- app del operario (cerrado)

Decisión de Miguel Ángel: app nativa Android en Kotlin, sin pasar por
una versión web previa, por el envío continuo de la posición en
segundo plano (ver 4.1). La instala y actualiza él; primeras pruebas
en su móvil. Aviso por WhatsApp con plantilla específica de asistencia
(ver 4.2).

### 5.2. Punto 2 -- sección Servicios y rol Supervisor de Asistencia (cerrado)

- Rol `ASSIST_SUPERVISOR` ("Supervisor de Asistencia") en
  `ivr_config.CompanyUser` (migración `ivr_config` 0049, aplicada).
- "Albarán (demo)" sustituida por "Servicios" (`ServicesHubView`,
  pestañas en el formato de Documentación), visible solo para ADMIN y
  ASSIST_SUPERVISOR (`AssistanceSupervisorAccessMixin`). El supervisor
  entra también a todo lo de Asistencia que antes era solo de
  administradores (56 vistas de `budgets/views.py`).
- **Cierre:** Miguel Ángel confirmó en el chat que Paloma ya tiene el
  rol de supervisora de asistencia y entra.

### 5.3. Punto 3 -- Fase 1: alta desde la foto de TIREA (cerrado)

- `budgets/tirea_extraction.py`: Gemini Vision lee la foto o PDF del
  albarán de TIREA con un esquema JSON y rellena el formulario de alta
  (`WorkOrderAssistanceForm`, `budgets/forms_services.py`); nada se
  guarda hasta confirmar. Alta a mano y edición de la orden en el
  mismo formulario.
- `budgets/assistance_resources.py`: conductores = usuarios activos de
  la sección "Asistencia" (default_role de la sección cambiado a
  DRIVER, decisión "2. (a)"); máquinas = familia ASISTENCIA de la
  flota; teléfono del conductor desde su `Contact` (el
  `CompanyUser.phone` está vacío en producción).
- **Cierre (verificado con consulta a BD):** orden **20261020002**
  creada desde una foto real de TIREA: Europ Assistance / Asistencia y
  Grúas Granada (aseguradora 80, tipo de vehículo 634, elegidos a
  mano), expediente ET26739160, cliente E.A.S.I.G., S.A.U., Mercedes
  Actros 2501JSP, código de proveedor GP700101, avería "BLOQUE MOTOR",
  fechas de solicitud, inicio, localizado y finalizado extraídas.
- La aseguradora no se elige sola con Europ Assistance porque hay dos
  con ese nombre (80, `EUROP_AGG`, y 81, `EUROP_TRANSGRUAL`) y TIREA
  solo pone "EUROP ASSISTANCE"; `_match_insurer` nunca adivina. El dato
  que las distingue lo aporta Pepe (responsable de asistencia).
- La orden 20261020001 (COVEI, sin datos) es una prueba anterior de la
  misma sesión.

### 5.4. Prueba completa del albarán en producción

Orden 20261020002, unidad 01 (José Antonio Zafra Peralta, grúa X11
9237LGN): aviso, albarán rellenado y firmado por Miguel Ángel en su
móvil (firma PNG de 38 KB en `WorkOrderAssistanceSignature`, estado
COMPLETED) y PDF descargado. Correcciones salidas de la prueba:
- PDF (`albaran_pdf.html`): la rejilla CSS grid se descolocaba en
  weasyprint; pasa a flex con anchos fijos. El chófer sale por su
  nombre completo (también en el detalle, el albarán y el
  desplegable). La avería no repite el código si es igual.
- Aviso por WhatsApp: "Notificado" significaba solo "Twilio lo
  aceptó". Ahora el aviso queda en **"Enviando aviso"**
  (`NOTIFY_SENDING`), Twilio informa por `status_callback` a
  `AlbaranNoticeStatusView` (`/api/whatsapp/albaran-status/<token>/`,
  token con la unidad firmada con la SECRET_KEY) y la unidad pasa a
  **"Notificado"** solo con *delivered*/*read*, o a **"Aviso fallido"**
  (`NOTIFY_FAILED`) con el código de error. Migraciones `budgets` 0031
  y 0032, aplicadas. El botón "Avisar" va por htmx y solo se
  sustituye la fila de la unidad (`_work_order_unit_row.html`), que se
  refresca cada 3 s mientras espera la confirmación.
- **Verificado en producción:** unidad 02 de la misma orden en "Aviso
  fallido" con "Twilio: undelivered, error 63016" (la plantilla
  `assistance_albaran_notice`, Content SID
  `HXa984de23fae56cb4afbeb1b6458f693c`, sigue pendiente de aprobación
  de Meta), visto por Miguel Ángel sin recargar la página.

### 5.5. Otros trabajos de la sesión

- **Botón "Volver"** (directriz 4.25 del documento maestro): vuelve a
  la página de la que se vino, con la pila de navegación de cada
  usuario en BD (`panel/navigation_history.py`,
  `PanelNavigationState` con `screen_key="back_stack"`). Aplicado a 36
  plantillas antiguas.
- **Gemini 3.5 Flash** rechaza `thinking_budget`: las 8 llamadas pasan
  a `ThinkingConfig(thinking_level="low")`.
- **PEP8** completo (flake8 a 0) en todos los archivos tocados,
  incluidos `budgets/views.py`, `budgets/models.py`,
  `whatsapp/views.py`, `whatsapp/services.py` y
  `work_order_processor/services.py`, con comprobación de AST
  idéntico.
- `PLATFORM_BASE_URL` como ajuste de `settings.py`; plantilla
  `work_order_create_direct.html` que faltaba desde H17.

## 6. Notas de S133: dudas para Pepe y decisiones de la reunión

Los apartados 6.0 y 6.1 (hoja de ruta de S133) quedan sustituidos por la
sección 7 (lo hecho en S133) y la sección 8 (hoja de ruta de S134). Se
conservan 6.2 y 6.3 con su numeración porque otros textos y commits los
citan así.

### 6.2. Dudas para Pepe (anotadas en S133)

Miguel Ángel, S133 (2026-10-21), verbatim: *"ahora ya anotamos todas
las dudas porque eso habrá que preguntarle a Pepe."* Se resuelven
cuando Miguel Ángel traiga las respuestas; hasta entonces no se toca
lo que dependa de ellas.

1. **Europ Assistance: Asistencia y Grúas Granada (80) o Transgrual
   (81).** Qué dato del albarán de TIREA distingue un servicio de una
   empresa y de la otra. Se aplica en `_match_insurer`
   (`budgets/views_services.py`). Es el dato del punto 3 de 6.1.
2. **Servicios encadenados: cómo se cierra en base el albarán
   anterior.** Desde S133 (commit `ab67c89`), un conductor y una
   máquina en "Regresando" se pueden asignar a otro servicio cercano
   sin volver a base (caso de Miguel Ángel: termina en Marbella y sale
   un servicio al lado, en Ojén). El albarán anterior se queda en
   "Regresando" sin cierre en base. Opciones planteadas:
   1. Cierre conjunto al llegar a base: una sola vez km finales y
      repostaje, y se cierran todos sus albaranes pendientes de cierre.
   2. Se cierra solo al encadenar: al asignar el siguiente servicio el
      anterior pasa a cerrado sin km ni repostaje; esos datos van en el
      último.
   3. Cada albarán por separado, cada uno con sus km y su repostaje.
   Relacionado: si los km finales de un albarán encadenado deben ser
   los del momento de terminar ese servicio o los de llegada a base.
3. **Envío al cliente del albarán resumen y de las copias firmadas.**
   Miguel Ángel, S133, verbatim: *"este albarán se puede enviar por
   correo junto con las copias firmadas al cliente una vez que esté.
   Otra cosa que tenemos que hacer que el albarán se pueda enviar al
   cliente. Es importante esto, tengo que consultarlo con Pepe."* Ya
   existe el albarán resumen de la orden (PDF, completo o parcial,
   S133); falta decidir con Pepe a quién se envía (cliente, aseguradora
   o los dos), por qué vía (correo, WhatsApp con la plantilla
   `albaran_customer_delivery`) y cuándo (al completarse o a mano).
   Es el punto 7 de 6.1 (fase 5 del dossier).

4. **Hoja de servicio (modelo que pasó Pepe, S133).** Implementada en
   S133 (servidor `5d20122`/`b3e61fd`, app `3565e15`). **Cerrada por
   Miguel Ángel (S133, 22/10/2026):** *"De momento damos ya todos los
   datos por válidos, festivos y nocturnos calculados por las tarifas
   que ya tenemos y por la configuración de horarios y calendarios de
   cada base, así como las bases que también están configuradas en
   BBDD."* Las decisiones de abajo quedan como están:
   1. **Km salida:** en el modelo viene como opcional; Miguel Ángel
      cree que es un fallo y se ha puesto obligatorio y como puerta de
      la hoja (*"si no mete la información inicial no le da acceso a
      la hoja de servicio [...] en principio ponlos obligatorios"*).
      Confirmar con Pepe.
   2. **"Base" (obligatorio, en la fila de Recogida y Destino):** se ha
      tomado como la base de llegada, junto a km y hora de llegada a
      base en el cierre. Confirmar.
   3. **Fotos:** en el modelo no llevan marca; se han hecho
      obligatorias las tres (antes de cargar, cargado en altura,
      descargado) antes de la firma, por la decisión E de la reunión,
      salvo reparación en el sitio (`repair_on_site`). Confirmar si
      "antes de cargar" también es obligatoria.
   4. **Matrícula y expediente opcionales y PMA obligatorio:** así
      viene en el modelo; se ha respetado tal cual.
   5. **Hora salida base:** en el modelo venía en rojo por error; la
      pone el conductor junto a los km de salida (corregido en S133).
   6. **Nocturno:** se calcula con la hora de salida de base y el
      horario nocturno de la aseguradora (o el de la empresa).
      Confirmar si cuenta la salida o la hora del servicio.

### 6.3. Reunión de Miguel Ángel con Pepe (S133, 21/10/2026) -- decisiones

Cambian el enfoque de la entrada de servicios y de la app del
conductor. Verbatim de Miguel Ángel donde importa.

**A. Entrada de servicios: tres puertas, sin correo ni web scraping.**
*"vamos a tener las tres entradas. Por foto, por llamada y por
WhatsApp. Nos olvidamos de controlar los correos."* El correo de TIREA
solo trae un enlace a su web (FlotaWEB) y el web scraping se descarta.
Lo que llegue de TIREA o de otra plataforma se mete por **foto**
(pantallazo, extractor ya hecho en S132); lo que llegue por teléfono,
quien lo recibe lo pasa **por WhatsApp o llamando al robot**.
Objetivo: *"el lanzamiento del albarán y del servicio debe ser
automático para quitar toda la carga de trabajo a la persona que da el
servicio [...] Todo el trabajo administrativo lo vamos a eliminar al
máximo."* Conversación natural: *"voy a enviar a Pepe, no, están
libres Antonio, Manolo y Fernando. Perfecto, pues Fernando."*

**B. Quién puede dar servicios por llamada o WhatsApp.** De momento,
los supervisores de asistencia (y los administradores). *"Nos
centramos solamente en que compruebe que la persona tiene servicios de
supervisión, de asistencia [...] luego ya si tenemos que dar más
permisos lo haremos."* Más adelante, una marca para trabajadores sin
acceso al panel.

**C. Manda quien da el servicio.** *"La orden de la persona que llama
prevalece sobre lo que tengamos en base de datos."* Si una máquina
figura en taller y quien da el servicio confirma explícitamente que ya
no lo está, se asigna igual y queda anotado.

**D. Servicios en cola.** *"Poder darle otro servicio para cuando
acabe el primero. O darle tres servicios."*

**E. WhatsApp sin plantilla:** la conversación la empieza siempre quien
da el servicio, dentro de la ventana de 24 h.

**F. Aseguradora por CIF.** El dato que distingue la aseguradora
(incluido el caso 80/81 de 6.2.1) es el CIF que trae el servicio
(pendiente de concretar con el documento).

**G. App del conductor (cambia la entrega del albarán):**
1. Km y hora de salida obligatorios **antes** de ver el albarán: *"No
   te puede aparecer el albarán hasta que introduzcas los datos que te
   estamos solicitando del vehículo. Y la hora de salida."* Sin ellos no
   ve ni la ubicación ni nada.
2. Fotos de la carga y de la descarga obligatorias **antes** de que
   aparezca la firma del cliente, y guardadas con el albarán.
3. Pepe dará una hoja con los datos que el albarán necesita.

**H. Todo el servicio guardado en base de datos y consultable por
cualquier dato, años después.** Regla, en palabras de Miguel Ángel
(S133): *"¿Qué se guarda? Todos los datos del albarán. ¿Por dónde se
busca? Por todos los datos del albarán."* Los datos que nombre
(número de albarán, operario, ayudantes, máquina, aseguradora, vehículo
asistido, tara, peso máximo autorizado, km de salida y de llegada,
horas de espera, fotos, firma, incidencias, cobro...) y las búsquedas
que ponga de ejemplo (por matrícula, por operario, por vehículo propio,
por incidencias, por aseguradora...) son **ejemplos, nunca una lista
cerrada**: *"cuando te doy un ejemplo [...] no es que te ciñas
solamente a lo que te estoy diciendo, como si fuera una lista
cerrada"*. Caso que lo ilustra: *"me acuerdo que un servicio
estuvimos 7 horas para sacar el camión"* → buscar "7 horas de espera"
tiene que dar los servicios con 7 horas de espera, y entre ellos se
reconoce el que se buscaba (por ejemplo, por el nombre del cliente).

Estado al anotarlo: nada se borra (los datos ya quedan guardados), pero
la búsqueda del listado de Albaranes (S133) solo mira unos pocos campos
de texto; la búsqueda por cualquier dato está por hacer.

**I. Exportación a TIREA y Prologic:** más adelante; *"De momento nos
vamos a centrar en la toma de datos."*

**Orden de trabajo acordado:** núcleo común de alta de servicios
(origen, regla de C, cola de D) → agente de WhatsApp → agente de voz
(IVR) → app del conductor (G) → consulta de servicios (H).

**Permisos para asignar (S133, 22/10/2026):** Alia solo propone
conductores que pueden llevar el tipo de máquina según su permiso de
conducir, CAP y carné de gruista en vigor (`MachineDriverRequirement`,
migraciones 0042-0044; `budgets/driver_qualification.py`). Tabla
acordada ("Perfecto"): asistencia en carretera C + CAP; cabeza tractora
(y cabeza tractora asistencia) CE + CAP; grúa móvil de 20/30 TM y
rescate con grúa móvil C + CAP + carné de gruista; vehículos de
personal B. Forzarlo exige nota y queda registrado ("Asignado pese
a..."). Las opciones de Alia van numeradas para contestar con el
número. Comprobado en producción: solo tienen ficha de persona con
permisos alvarez_admin (B), carlos.carlin (C/CE + CAP + gruista) y
joseantonio.zafra (CE + CAP); el resto de usuarios que salen como
conductores no tiene ficha de persona enlazada y Alia no los propone.

**Fuera de H37 (S133, 22/10/2026) -- Herramientas de contabilidad:**
entrada propia en la barra lateral (mismos roles que Costes de
operarios) con dos uniones de CSV: carpeta, lista alfabética
reordenable arrastrando, Generar y Descargar
(`analytics/accounting_csv.py`, `analytics/views_accounting.py`).
Asientos: B correlativa por asiento original, C renumerada 1, 2, 3
dentro de cada asiento sin mover filas, K vacía. Facturas: una
cabecera, ORDEN correlativo, ASIENTO como contador de facturas según
la columna Factura, y una sola línea resumen final con BASE, CUOTA y
TOTAL sumados. Probadas y dadas por correctas por Miguel Ángel y
Jerónimo.

**Pendiente técnico anotado en S133 (directriz 4.9):**
`vox_bridge/services.py` pasó de ~750 avisos de flake8 a 68 (repaso
automático con AST idéntico más imports sin uso retirados). Las 68
restantes son líneas largas dentro de los manejadores de herramientas
de la llamada, con ~10 niveles de anidación: arreglarlas bien exige
sacar cada manejador a su propio método, y eso hay que validarlo con
llamadas reales al robot. Se hace en la sesión en que se pruebe la
llamada para dar servicios.


## 7. COMPLETADAS EN S133 (21-23/10/2026, PEE PC; H37 fases 2 a 4, Alia como jefa de tráfico, y fichajes y Partes Digitales)

65 commits (`5b774e6..856f19d`), 79 archivos, 15 migraciones aplicadas
por `deploy.yml` sin error (`budgets` 0033-0046 y
`work_order_processor` 0034).

### 7.1. Servicios de asistencia (H37)

- **Panel de tráfico (fase 2, punto 4 de la hoja de S132):** tarjetas
  de conductores, máquinas y albaranes, asignación arrastrando y envío
  (`56714fb`). Equipos conductor+máquina, intercambio de máquinas, mapa
  y pantalla completa (`4daefcc`). Conductores y máquinas en columnas
  separadas (`1e7d698`). Un conductor y una máquina que regresan a base
  se pueden asignar al siguiente servicio (`ab67c89`).
- **App del conductor:** API con token y albaranes asignados
  (`f5585d6`), detalle del albarán y envío firmado o sin firma con
  motivo (`2c0149e`), y cierre en base con km finales y repostaje
  (`4eaeaae`). Cierre en base también desde el panel, con km y gasoil
  estimados (`444f934`). Hoja de servicio de Pepe: los km de salida son
  la puerta de la hoja, y van fotos (`5d20122`, `b3e61fd`). La hora de
  salida de base la pone el conductor (`ddddae5`).
- **Ayudantes por albarán y albarán resumen de la orden** en PDF
  (`47fef39`). Listado de albaranes con el formato 4.24 (`3b430ba`).
  Para las pruebas, los administradores también salen como conductores
  (`8f0629a`).
- **Alta de servicios por las tres puertas de la reunión con Pepe
  (6.3):**
  - Origen del servicio, cola y asignación forzada (`4e18b49`).
  - Alia por WhatsApp (`4a9f704`, `8b381ff`, `52daa66`, `4032c7c`).
  - Llamando al robot con las mismas herramientas (`93651b8`).
  - Alta por CIF, con dos lecturas de respaldo del CIF de TIREA
    (`4b167f1`, `2f6b12b`).
  - Alia decide desde el conductor parado y lanza varios equipos
    (`b69471c`). Remolca tractora y semirremolque juntos y cuenta con
    los conductores en cola (`e85342b`).
  - Propone solo conductores con el permiso de conducir, el CAP y el
    carné de gruista que pide la máquina, con opciones numeradas
    (`3274202`, `a80642c`, tabla en 6.3).
- **Ajustes tras pruebas reales con Miguel Ángel por WhatsApp:**
  - Anular albarán desde el tablero, con motivo obligatorio y unidad
    en `CANCELLED` (`49ef64c`). Liberó a Zafra del albarán de prueba
    20261021003-01.
  - Los comentarios de quien da el servicio mandan sobre los campos de
    relleno de TIREA (`1e6e36b`).
  - Se guardan todos los datos del servicio: matrícula del 2.º
    vehículo, C.P. de entrega y el resto de campos de la orden, que Alia
    puede usar (`d14b189`).
  - Alia contesta aunque la lectura del PDF tarde: conexión MySQL
    renovada tras la llamada larga a Gemini (`65c728f`).
  - Una reparación en el sitio va con VEHÍCULO DE PERSONAL, nunca con
    grúa (`3099f0d`).
  - El documento se lee primero como texto (PDF o Cloud Vision), en
    unos 4-5 s; solo si no hay texto se lee el archivo (`e99d7d5`).
  - Reintentos con espera ante un 429/503 de Gemini, con aviso
    "estoy saturada" al usuario si no se recupera (`8037f19`).
- **Fuera de H37:** Herramientas de contabilidad (`f9b0a2b` a
  `76d0eff`, descritas en 6.3), y nombre y apellidos de la cuenta
  editables desde la edición de usuario (`285a1d6`).

### 7.2. Fichajes y Partes Digitales (H24/H07, Caso A del enrutador: anotado aquí porque se hizo en esta sesión)

- **Se ficha solo al inicio y al fin de la jornada** (`67e74fb`): un
  único tramo de la primera entrada a la última salida. La pausa de
  comida es la del parte: sale del horario y se cambia a mano, como
  antes de los fichajes. La pestaña Fichajes descuenta esa pausa
  (`d9948b2`).
- **"Nuevo parte" pasa a ser un aviso para los operarios** antes del
  formulario (`WorkshopNotice`, migración 0034, `d77a801`). Lo editan
  ADMIN y WORKSHOPBOSS. Miguel Ángel puso el texto del aviso de los
  fichajes.
- **No se liquida un periodo con partes sin revisar** (`0e24666`).
  Causa de la incidencia 6.0.A de S132 y de que Carolina no viera los
  revisados: el periodo Septiembre-Octubre 2026 se liquidó con 113
  partes sin revisar. Miguel Ángel lo reabrió.
- **Horas festivas** (`ff6ff0c`). Sábado, domingo y festivo de la base
  del trabajador; no son ni extras ni ordinarias. Columna, total y
  orden propios en el listado (`work_order_processor/festive.py`).
- **Partes Digitales con el formato 4.24** (`c481c4b`, PEP8 previo en
  `19838a3`). Panel fijo arriba, lista con scroll, selección
  persistente y orden de hasta 4 niveles. La fila TOTAL de Revisados
  queda fija abajo.
- **El parte se guarda aunque el fichaje no cuadre** (`0a55293`,
  `856f19d`), por la incidencia de Antonio Fontalba del 22/10.
  - Quería cerrar el parte antes de fichar la salida y el botón estaba
    desactivado. Miguel Ángel: *"que el botón se quede habilitado, que
    puedan guardar [...] cuando fiche, si hay una discrepancia de hora,
    decirle, no están bien las horas, pero que se quede guardado."*
  - Ahora "Cerrar parte" siempre está activo. Si solo falla el fichaje
    (falta la salida o las horas no cuadran), el parte queda guardado
    en curso, con aviso amarillo del motivo y sin Excel, porque generar
    el Excel marca el parte como cerrado.
  - Al fichar la salida, la página de fichaje dice si el parte se ha
    cerrado o qué hora no cuadra (`ClockOutOutcome` en
    `hr_calendar/clock_parts.py`, `parte_notice` en la respuesta de
    `/fichaje/`).
  - Probado en local, con el caso de Antonio y los dos casos de horas
    que no cuadran.
- **Sampaio, parte 702** (incidencia 6.0.B de S132): resuelto en esta
  sesión. El domingo 18 queda como parte propio, el 708 (B43, de 18:30
  a 21:30, 3 h festivas), y el 702 como el martes 20 completo
  (comprobado con consulta a BD el 23/10).
- **Pablo Cañamero, partes del 24/09 y del 16/10:** no se pueden
  recuperar. No llegaron nunca al servidor: no hay rastro en BD (ni
  borradores) ni en ningún log rotado, y Pablo no tiene fichajes. Los
  tiene que volver a meter él.

### 7.3. Herramientas

`file_fetch.yml` admite `grep_pattern` (`b8c9b0e`): busca una expresión
en varios logs rotados a la vez (también dentro de los `.gz`) con
`remote_path` con comodines, y solo sube a Drive las líneas que
coinciden. Los logs INFO de Django de la web (`[SAFETY-LOG]`,
`[PARTE-BACKUP]`, `[FICHAJE]`...) están en
`/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.error.log*`,
no en `server.log`.

## 8. Hoja de Ruta para la Siguiente Sesión (S134) -- reescrita al cierre de S133

Se hace en este orden.

1. **Parte guardado que arrastra cualquier parte nuevo** (6.0.C de
   S132, decisión de Miguel Ángel en S133: opción 1).
   - Hoy, con un parte en curso, el formulario siempre lo abre y lo que
     se guarda o se cierra va a ese parte, aunque el operario cambie la
     fecha (`WorkOrderEntryFormView`: búsqueda del `IN_PROGRESS` del
     operario en GET, en guardar y en cerrar). Desde S133 pasa más,
     porque un parte cuyas horas no cuadran con el fichaje queda en
     curso.
   - Hacer: avisar al operario de que tiene un parte en curso de otro
     día y dejarle elegir entre seguir con ese parte o empezar uno
     nuevo. El parte en curso se conserva aparte, sin perder nada.
   - **Cierre:** prueba en local con un parte en curso del día D y un
     parte nuevo del día D+1. Consulta a BD con dos `WorkOrder`
     distintos, uno por fecha, cada uno con sus propias líneas.
2. **Tablero de tráfico de Servicios** (captura de Miguel Ángel del
   23/10).
   - En pantalla completa del tablero no hay botón para volver al
     estado normal. Añadirlo con el formato de la directriz 4.26.
   - Las tarjetas de usuarios (conductores) son más estrechas que los
     nombres: "Alberto Álvarez D...", "Alejandro Sergio" y "José Luis
     Álvarez" salen cortados y se salen de la tarjeta.
   - **Cierre:** captura con Playwright del tablero en pantalla
     completa y en normal. Botón visible que devuelve al estado normal.
     El nombre completo de los conductores dentro de su tarjeta,
     comprobado con `scrollWidth <= clientWidth` en cada nombre.
3. **Alia elige el vehículo adecuado al trabajo.** Según haya que
   remolcar, levantar vehículos o sustituir neumáticos, ruedas,
   baterías, etc. (Miguel Ángel, S133).
   - Partir de los criterios de asignación actuales
     (`DISPATCH_CRITERIA` en `budgets/service_intake.py`, que ya manda
     la reparación en el sitio con VEHÍCULO DE PERSONAL) y de los tipos
     y familias de la flota de asistencia.
   - **Cierre:** un caso de prueba de Alia por tipo de trabajo, en
     local y por WhatsApp en producción con Miguel Ángel, con el tipo
     de vehículo propuesto correcto en cada uno: remolque, elevación y
     cambio de neumático o rueda, de batería, etc.
4. **Resto de H37, en el orden de la reunión con Pepe (6.3):**
   1. **Consulta de servicios por cualquier dato (6.3.H).** La búsqueda
      del listado de Albaranes solo mira unos pocos campos. **Cierre:**
      una búsqueda por "7 horas de espera" (o el dato equivalente de un
      servicio real) que devuelve los servicios con ese dato.
   2. **Quitar a los administradores de la lista de conductores.** Se
      añadieron en `8f0629a` solo para las pruebas.
      **Cierre:** el panel de tráfico sin `alvarez_admin` ni
      `coco.alvarez` como conductores.
   3. **Plantilla `assistance_albaran_notice` de Meta.** Cuando Miguel
      Ángel indique que está aprobada, pulsar "Avisar de nuevo" en una
      unidad real. **Cierre:** unidad en `NOTIFIED`, con `notified_at`
      relleno y `notify_error` vacío.
   4. **Prueba del robot de voz para dar servicios**, con el repaso
      pendiente de `vox_bridge/services.py` (6.3, pendiente técnico).
      **Cierre:** un servicio dado de alta llamando al robot en
      producción, y flake8 a 0 en ese archivo.
   5. **Lo que depende de Pepe (6.2):** aseguradora 80/81 por CIF,
      cierre en base de servicios encadenados y envío al cliente. Se
      hace cuando Miguel Ángel traiga sus respuestas.
   6. **Exportación a TIREA y Prologic:** más adelante (6.3.I).

## 9. COMPLETADAS EN S134 (23/10/2026, PEE PC; puntos 1, 2, 3, 4.1, 4.2 y 4.4 de la hoja de S134, y estimados de tiempo con cola en dos modos)

Sesión pausada por PCH a H31 (Miguel Ángel: *"Necesito pivotar hacia
documentación"*). La hoja de ruta de la sección 8 queda tal cual; aquí
se anota lo hecho de cada punto.

### 9.1. Punto 1 -- parte en curso de otro día (H07, Caso A) -- `d3332ad`

- "Nuevo parte" abre el parte en curso de hoy. Si solo los hay de otros
  días, pregunta: seguir con uno o empezar uno nuevo
  (`form_in_progress_choice.html`; `?parte=<pk>` y `?nuevo=1`). Los
  demás partes en curso salen avisados en el formulario.
- Guardar tareas y Cerrar parte sin parte señalado crean uno nuevo,
  nunca toman el primer parte en curso del operario.
- Otro parte en curso de la misma fecha cuenta como fecha duplicada,
  con enlace para seguir con él; el error conserva el parte que se
  estaba guardando (antes se perdía y el siguiente envío creaba otro).
- **Probado en local:** parte en curso del 22/10 y parte nuevo del
  23/10, dos `WorkOrder` distintos, cada uno con su línea.

### 9.2. Punto 2 -- tablero de tráfico -- `7a1700b`

- Botón "Salir de pantalla completa" dentro del panel (el de la barra
  superior queda fuera de la pantalla completa).
- Nombres de conductores enteros: `min-w-0` no existe en Bootstrap 5.3
  y el bloque del nombre no encogía.
- **Probado en local con Playwright:** `scrollWidth <= clientWidth` y
  nombre dentro de la tarjeta en tres nombres largos; el botón solo se
  ve en pantalla completa y devuelve al estado normal.

### 9.3. Punto 3 -- Alia elige el vehículo según el trabajo -- `acdd445`, `8a2680c`, `b1c1be4`

- `budgets/dispatch_vehicle.py`: trabajo según los datos del servicio
  y tipos reales de la flota que lo hacen:
  - remolcar ligero: ASISTENCIA EN CARRETERA;
  - remolcar pesado: RESCATE / GRÚA MÓVIL;
  - levantar: GRÚA MÓVIL / RESCATE;
  - rueda, batería, combustible y averías pequeñas: VEHÍCULOS DE
    PERSONAL;
  - semirremolque: CABEZA TRACTORA, en otro equipo.
- `guardar_datos` y `consultar_disponibilidad` le dan a Alia el trabajo
  detectado y para qué sirve cada máquina.
- Con la hoja real de Web Flota que pasó Miguel Ángel (RACC,
  OT4526068), la lectura de TIREA pasa a recoger "Reparación in situ"
  y "Accidente", y se reconoce "NEUM".
- Criterio 6: el tipo lo decide el trabajo, nunca quién está libre.
- **Prueba de Miguel Ángel por WhatsApp** con seis servicios de prueba
  generados con el formato de Web Flota, marcados PRUEBA:
  - cinco tipos correctos a la primera;
  - en el vuelco, Alia propuso primero la plataforma porque Zafra no
    tiene carné de gruista. Corregido con el criterio 6.

### 9.4. Punto 4.1 -- búsqueda por cualquier dato -- `614a2e3`

- `budgets/assistance_search.py`: cada dato guardado de la orden, el
  albarán, su incidencia, su firma, sus ayudantes y su historial es
  una frase «valor etiqueta» sacada de los campos del modelo.
- Cada número tiene que estar en un dato cuya etiqueta lleva las
  palabras dichas a su lado.
- **Probado en local:** once búsquedas; «7 horas de espera» no da los
  de 7 horas de rescate.

### 9.5. Punto 4.2 -- administradores fuera de la lista de conductores -- `f026d02`

**Comprobado en producción** (consulta a BD): conductores de
asistencia = solo `joseantonio.zafra`.

### 9.6. Punto 4.4 -- robot de voz, flake8 a 0 -- `b4085ac`

- Cada manejador de herramienta del bucle de `_receive_gemini_audio`
  pasa a su método, con cuerpo idéntico en AST al original.
- flake8 a 0 en `vox_bridge/services.py`; desplegado con el reinicio
  del bridge.
- **Falta la llamada real al robot** para validarlo.

### 9.7. Estimados de tiempo y cola en dos modos -- `924d83c`

Pedido por Miguel Ángel en S134 tras la prueba del punto 3 (no había
segundo conductor para el caso de dos equipos). Verbatim:
- *"ver las horas y bueno, los kilómetros hasta el punto de recogida
  [...] tener estos tiempos de finalización ya calculados una vez que
  se lanzan los servicios"*;
- *"Hay que enviar el aviso en cola con vuelta a base o en cola desde
  donde esté. Tenemos que tener esas dos opciones [...] si viene un
  camión de vuelta, pasa cerca, entonces le decimos a ese que
  directamente recoja él"*.

Tiempos de trabajo fijados por él: carga 30, descarga 30, reparación
in situ 30, levantar un vehículo 60 min (`AssistanceTimes`, uno por
empresa, sin pantalla para editarlos todavía).

Qué se ha hecho:
- Migración `budgets` 0047. **Comprobada en producción** por consulta
  a BD: migración aplicada, 7 columnas nuevas y la tabla de tiempos.
- `budgets/service_eta.py`:
  - matriz de rutas de Google con tráfico, desde la última posición del
    móvil o la base;
  - encadena el albarán en curso y los de la cola;
  - se recalcula al asignar, al quitar, al cambiar la cola y en cada
    cambio de estado.
- Cola con vuelta a base (por defecto): sale al cerrar en base el
  anterior. Desde donde esté: sale al terminarlo.
- Tablero: llegada, fin y km de cada albarán, botón para cambiar la
  cola y hora de fin de los equipos ocupados.
- Alia (WhatsApp y llamada):
  - recibe a qué hora llegaría cada equipo a la recogida, por los dos
    caminos;
  - lanza con el argumento `cola`.
- `deploy.yml` reinicia bridge y worker también por `dispatch_vehicle`,
  `service_eta` y `driver_qualification`.

**Probado en local** con trayectos fijos: horas encadenadas, los dos
modos, salida de la cola y llegada de un equipo ocupado.

**Pendiente:** la prueba en producción con Google real. Decidido por
Miguel Ángel al cierre de S134: se hace con un usuario chófer de
pruebas suyo, sin tocar a ningún conductor real. **Cierre:** un
servicio de prueba asignado a ese usuario con otro en cola; consulta
a BD con `eta_pickup_at`, `eta_finish_at` y `eta_km` rellenos en los
dos, y `eta_detail` sin error de Google.

### 9.8. Recibido en S134 para más adelante

Documentación de la API de GasoGes Web, para actualizar km y horas de
las máquinas. Miguel Ángel: *"en la siguiente sesión"*. Guardada en
`DOCS_ATTACHED_2_ANNEX_V30/Documentacion_API_GasoGes_v1.3.pdf`
(`51a268c`):
- API de solo consulta (GET) con autenticación básica;
- las credenciales las da GasoGes y no van en el repositorio.

### 9.9. Al cierre de S134

- La sesión acabó en H31 (foto de carné, ver su anexo) y la siguiente
  va a H30, con la integración de GasoGes (km y horas de las máquinas
  para los avisos). Miguel Ángel: *"Pasamos a la siguiente sesión con
  esto y luego volvemos con asistencia."*
- La hoja de ruta de la sección 8 sigue intacta. Lo que queda de ella
  está en el resumen de arriba.
