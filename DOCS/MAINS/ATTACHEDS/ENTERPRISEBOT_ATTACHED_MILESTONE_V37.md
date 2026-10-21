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

## 6. Hoja de Ruta para la Siguiente Sesión (S133) -- reescrita al cierre de S132, sustituye a la de S132

### 6.0. Incidencias de Partes Digitales anotadas en S133 -- primera tarea de la siguiente sesión

Son de Partes Digitales (H07/H20), no de H37. Se anotan aquí porque
Miguel Ángel pidió resolverlas en la siguiente sesión, antes de seguir
con la hoja de ruta de abajo (Caso A del enrutador: al resolverlas, el
trabajo se registra en el anexo del hito donde vive el error).

**A. Periodos liquidados con partes pendientes, y partes que no salen
en el historial.** Miguel Ángel, S133 (2026-10-21), verbatim: *"anota
esta incidencia de periodos liquidados y partes que no están en el
historial, para resolverla en la siguiente sesión."* Lo que enseñan
sus capturas de Partes Digitales
(`/panel/work-orders/history/`):
- Pestaña **Períodos**, operario Estevao Veloso Sampaio: los seis
  periodos salen **Liquidado** (Septiembre-Octubre 2026, 21/09-20/10;
  Agosto-Septiembre; Julio-Agosto; Junio-Julio; Mayo-Junio; y
  "anteriores", 01/01/2000-20/05/2026), con columna Operarios 9/9,
  8/9, 3/9, 5/9, 5/9 y 3/9. Contadores de Sampaio en ese filtro:
  Pendientes 23, Revisados 11.
- Pestaña **Pendientes**, todos los operarios, 01/01/2026-21/10/2026:
  **190** partes pendientes, con fechas de mayo a julio de 2026 (p. ej.
  David Contreras Marquez desde el 21/05/2026, Jose Antonio Vargas Mora
  18/06/2026), es decir, dentro de periodos que ya salen liquidados.
- Pestaña **Revisados**: 92 (p. ej. Carlos Bas Blanco junio-julio,
  revisados por Alejandro Sergio el 13/08/2026).
Qué hay que averiguar: cómo puede estar liquidado un periodo con
partes sin revisar dentro (y qué significan 3/9, 5/9...), y qué partes
faltan en la pestaña **Histórico** y por qué. Antes de tocar nada,
consulta a BD de los periodos (`WorkPeriodGroup` y relacionados,
`panel/views_workorders.py`) y de los partes de esas fechas, y
pregunta a Miguel Ángel qué esperaba ver en cada pestaña si no queda
claro con los datos (directriz 4.8).

**B. Parte 702 de Sampaio (domingo 18 mezclado con martes 20).** El
borrador del domingo 18 (bloque B43, 08:00-15:30, 6 h, creado el 19 a
las 19:04 con "Guardar bloques") no se pudo cerrar por el mínimo de 8 h
en festivo (corregido en S133, commit `d6ab7bc`). El formulario
siempre abre el borrador pendiente del operario y, al hacer el parte
del martes 20, Sampaio cambió la fecha y añadió el bloque B12
(15:30-18:30, 3 h): el parte 702 quedó con fecha 20/10 y los dos
bloques. Pendiente: su respuesta a las preguntas enviadas por WhatsApp
el 20/10 (qué hizo el domingo y el martes completos) y la decisión de
Miguel Ángel entre (1) separar el parte con un Comando S, (2) que lo
corrija Sampaio desde el panel o (3) dejarlo.

**C. Borrador que arrastra cualquier parte nuevo.** Con un borrador
abierto, guardar bloques o cerrar escribe siempre en ese borrador,
aunque el operario cambie la fecha (`WorkOrderEntryFormView`, búsqueda
del `IN_PROGRESS` del operario en guardar y cerrar). Decisión
pendiente de Miguel Ángel: (a) avisar y dejar elegir entre seguir el
borrador o empezar un parte nuevo, con el borrador conservado aparte
(cambio de vista y de servidor), o (b) no dejar cambiar la fecha de un
borrador guardado.

### 6.1. Hoja de ruta de H37

Ordenada con las fases del dossier de Pepe (4.4), a petición de Miguel
Ángel en S132. Los puntos 1 a 3 quedaron cerrados en S132 (ver 5.1 a
5.3); se mantiene la numeración para no perder la correspondencia con
el dossier.

Datos de partida fijados por Miguel Ángel en S132:
- **Máquinas de asistencia:** las de la familia ASISTENCIA de la flota
  (`fleet.MachineAsset.family`).
- **Conductores de asistencia**, verbatim: *"Conforme se vayan dando de
  alta trabajadores irán entrando en la sección. Ya debería de haber un
  trabajador."* Son los trabajadores de la sección Asistencia.

Se hace en este orden.

1. **Forma de la app del operario.** Cerrado en S132 (5.1).
2. **Sección Servicios.** Cerrado en S132 (5.2).
3. **Fase 1 del dossier.** Cerrado en S132 (5.3).
   Queda una mejora atada a un dato externo: cuando Miguel Ángel
   aporte el dato de Pepe que distingue en el albarán de TIREA un
   servicio de Asistencia y Grúas Granada de uno de Transgrual, usarlo
   en `_match_insurer` (`budgets/views_services.py`) para elegir solo
   entre las aseguradoras 80 y 81. **Cierre:** una foto de TIREA de
   Europ Assistance que deja la aseguradora correcta y su tipo de
   vehículo ya elegidos en el formulario.
4. **Fase 2: panel de tráfico y asignación.** Pestaña principal de
   Servicios: columnas de tarjetas de conductores, máquinas y
   albaranes abiertos con los colores del dossier (4.4), asignación
   arrastrando, sin dejar asignar lo ocupado ni lo que está en taller,
   y botón de enviar, que manda el aviso por WhatsApp con la plantilla
   `assistance_albaran_notice` (4.2, creada en S132, Content SID
   `HXa984de23fae56cb4afbeb1b6458f693c`, pendiente de aprobación de
   Meta). Ya hecho en S132: el aviso con su confirmación de entrega
   ("Enviando aviso" → "Notificado" / "Aviso fallido", 5.4); el botón
   de enviar del panel reutiliza `send_operator_albaran_notification`.
   Cada cambio de estado guarda hora y usuario. **Primera tarea de
   S133:** si Miguel Ángel indica que Meta ya aprobó la plantilla,
   pulsar "Avisar de nuevo" en la unidad 20261020002-02. **Cierre de
   esa tarea:** consulta a BD con la unidad en NOTIFIED, `notified_at`
   relleno y `notify_error` vacío. **Cierre del punto:** un servicio
   asignado arrastrando y enviado en producción, con conductor y
   máquina en estado ocupado y la unidad en NOTIFIED en BD.
5. **Fase 3: vista del conductor y firma.** Hoja del conductor sin
   notas internas ni importes, km de salida, fotos, firma del cliente
   o motivo de no firma; al firmar, albarán en verde y conductor y
   máquina regresando. Aquí va la prueba completa con un albarán real
   de Allianz, cotejando los campos de la sección 3.1 (en S132 ya se
   probó la cadena completa con un servicio real de Europ Assistance:
   albarán rellenado y firmado en el móvil y PDF, ver 5.4). Después, la app
   nativa Android en Kotlin (4.1): repositorio propio NewFlow,
   compilación por GitHub Actions, albarán sin conexión que se envía
   al volver la cobertura, segundo plano con envío continuo de la
   posición, y el mapa del panel con servicios, vehículos y bases.
   Miguel Ángel instala y actualiza la app; primeras pruebas en su
   propio móvil. **Cierre:** tres consultas a BD. Un albarán de Allianz
   firmado en producción. Otro rellenado y firmado en modo avión que
   llega al recuperar la conexión, con `signed_offline=True` y
   `synced_at` relleno. Posiciones del móvil de Miguel Ángel
   registradas con la pantalla apagada.
6. **Fase 4: cierre en base con km y gasoil.** El conductor mete km
   finales y si repostó y cuántos litros; el albarán pasa a cerrado
   (gris) y conductor y máquina vuelven a libres. Sin km finales ni la
   indicación de repostaje no se puede cerrar. Decisión S132: el
   estado final de un albarán firmado en pantalla es este cierre en
   base; *Firma recibida* queda solo para el albarán cerrado sin firma
   cuyo papel firmado llega después. **Cierre:** un servicio real
   cerrado en base, con sus km y litros en BD y conductor y máquina de
   nuevo libres.
7. **Fase 5: historial, buscador, PDF y envío al cliente.** Servicios
   cerrados archivados, buscador del apartado 26 del dossier,
   exportaciones del 27, y el envío del albarán firmado al cliente con
   la plantilla `albaran_customer_delivery`. Los albaranes no se
   borran: se corrigen con registro de auditoría. **Cierre:** un
   albarán real encontrado con el buscador, su PDF descargado y el
   envío recibido en el teléfono de prueba que indique Miguel Ángel.
8. **Fase 6: mantenimiento y avisos.** Km y próximo mantenimiento de
   cada máquina de asistencia, sobre los avisos de revisiones de H30, y
   las alertas del apartado 25 del dossier. **Cierre:** una alerta real
   generada en producción.
9. **Fase 7: estadísticas y facturación.** Apartados 17 y 18 del
   dossier. **Cierre:** las estadísticas del apartado 17 calculadas en
   el panel sobre los servicios reales de BD, coincidentes con una
   consulta a BD de los mismos servicios, y la facturación del
   apartado 18 de un servicio real cerrado, con su importe en BD.

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

