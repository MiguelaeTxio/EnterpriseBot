# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V04.md

# Anexo de Hito V04 — Canal WhatsApp: Chatbot Conversacional y Sistema de Presencia
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-04-09
# Prerequisito: Hito 3 (Estrategia B IVR)

---

## 1. Visión General del Hito

Este hito incorpora WhatsApp como canal de comunicación bidireccional en
EnterpriseBot, construido íntegramente sobre la infraestructura Twilio ya
existente. Opera en dos dimensiones complementarias:

**Dimensión 1 — Cierre del bucle de presencia del Hito 3:**
El sistema de presencia diseñado en el Hito 3 quedó con dos piezas
pendientes explícitamente diferidas a este hito: el webhook de respuesta
a recordatorios en `/api/whatsapp/presence/` y las tareas Celery
`check_in_meeting_reminders` y `expire_presence_statuses`. Este hito las
implementa y valida completamente, cerrando el sistema de presencia de
extremo a extremo.

**Dimensión 2 — Chatbot de atención al cliente por WhatsApp:**
Un agente conversacional inteligente, impulsado por Gemini (modelo de
texto, no Live), que atiende consultas entrantes de clientes por WhatsApp.
El agente conoce la estructura de la empresa (secciones, contactos,
disponibilidad en tiempo real por PresenceStatus) y puede informar,
derivar y capturar datos, todo desde la misma base de datos multiempresa
construida en el Hito 3.

La empresa piloto es **Grupo Álvarez** (Grúas Álvarez).

---

## 2. Decisiones Arquitectónicas y Tecnológicas

### 2.1. Plataforma: Twilio for WhatsApp

**Decisión tomada en sesión 2026-04-09.** Se descartó la integración
directa con Meta Cloud API. Fundamentos:

- El SDK twilio 9.10.4 ya está instalado en EnterpriseBot_venv.
- Las credenciales (TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID,
  TWILIO_API_KEY_SECRET) ya están configuradas en el entorno.
- El patrón webhook/TwiML/Django ya está dominado desde el IVR.
- El Sandbox de Twilio para WhatsApp permite desarrollar y probar sin
  necesidad de verificación Meta Business completa.
- Sinergia futura: desde finales de 2025, Twilio soporta llamadas de voz
  por WhatsApp, abriendo la posibilidad de escalar de chat a llamada en el
  mismo hilo en un hito posterior.
- Coste del sobrecargo Twilio ($0.005/mensaje) irrelevante al volumen de
  operación de Grupo Álvarez.

### 2.2. Modelo de IA para el chatbot de texto

**Modelo:** gemini-2.5-flash (Vertex AI) vía google-genai 1.69.0.

**Fundamento:** El canal WhatsApp es texto puro, no audio en tiempo real.
No se usa el modelo Live (gemini-live-2.5-flash-native-audio) porque:
- El modelo Live está diseñado para sesiones de audio A2A en tiempo real
  con WebSocket persistente, patrón incompatible con la naturaleza
  stateless de los webhooks de WhatsApp.
- gemini-2.5-flash es el modelo de texto de referencia en Vertex AI, más
  eficiente y económico para generación de texto conversacional.

**API utilizada:** `client.chats.create()` / `chat.send_message()` del SDK
google-genai. La sesión de chat se gestiona de forma manual en BD (modelo
WhatsAppSession), reconstruyendo el historial en cada llamada al webhook.

**Autenticación:** Vertex AI vía Service Account JSON, idéntico al IVR.
Variables de entorno: GCP_CREDENTIALS_PATH, GOOGLE_CLOUD_PROJECT,
GOOGLE_CLOUD_LOCATION.

### 2.3. Gestión de números de Grupo Álvarez en Twilio

**Estado final (producción activa):**

- **+34607961650** — WhatsApp sender principal. REGISTRADO Y OPERATIVO.
  Sender status: Online. Throughput: 80 MPS.
  WhatsApp Business Account ID: 950408527754677.
  Meta Business Manager ID: 2762307714126800.
  Webhook configurado: `https://enterprisebot-miguelaetxio.pythonanywhere.com/api/whatsapp/incoming/`
  Sembrado en BD: pk=5, capabilities=BOTH, is_active=True.
  Variable de entorno: TWILIO_WHATSAPP_SENDER=+34607961650 (en .env).
  Verificación E2E superada: sesión creada en BD, chatbot responde con
  coherencia corporativa de Grupo Álvarez desde número de producción.

  **Historial del proceso de registro:**
  Los Twimlets (`twimlets.com/voicemail`) están marcados como obsoletos en
  2026. El método correcto utilizado fue una **Twilio Function** mínima
  durante la verificación Meta (10-15 min). Twilio Function desplegada:
  `whatsapp-verify-4871.twil.io/whatsapp-verify`.
  Ticket de soporte Twilio #26344158 (P2 High, 2026-04-16) para reset del
  contador OTP en +34951799117 — resuelto durante el fin de semana del
  19-20 de abril.
  Ver documento satélite: `DOCS_ATTACHED_2_ANNEX_V04/V04DOC_WHATSAPP_NUMBER_REGISTRATION.md`

- **+34951799117** — Reservado para IVR de voz.
  Voice Configuration IE1: gestionada por voice_orchestrator.py al
  arrancar.

- **+34951796832** — Reservado para pruebas IVR de voz.
  Voice Configuration IE1: apunta a ngrok (gestionado por orchestrator).

- **+14155238886** — Sandbox Twilio (desarrollo). Sembrado en BD,
  capabilities=BOTH. Código de unión Sandbox: join kept-title.

**Nota crítica:** Las plantillas se gestionan exclusivamente a través del
Content Template Builder del Console de Twilio o la Content API. Los
templates tienen SID con prefijo HX y se envían vía el parámetro
ContentSid en la API de mensajería.

### 2.4. Ventana de sesión de 24 horas (regla Meta)

Desde julio de 2025, Meta aplica un modelo de precios por mensaje. Las
reglas de sesión son:

- Mensajes de sesión (ventana 24h): cuando un usuario envía un mensaje a
  la empresa, se abre una ventana de 24 horas desde el último mensaje
  recibido. Durante esta ventana se pueden enviar mensajes de texto libre
  sin template, sin coste de template Meta (solo el fee Twilio de
  $0.005/mensaje).
- Mensajes fuera de sesión (business-initiated): requieren template
  aprobado por Meta, enviados con ContentSid=HX... Se aplica el fee de
  template Meta según categoría (marketing, utilidad, autenticación).
- Templates de utilidad dentro de la ventana: gratuitos (fee Meta = $0).
- Templates de utilidad fuera de la ventana: tienen coste Meta.
- Mensajes de recordatorio de presencia: se envían como templates de
  utilidad (UTILITY), pre-aprobados por Meta antes de su uso en
  producción.

### 2.5. Arquitectura de la app Django whatsapp

App Django `whatsapp` dentro del proyecto EnterpriseBot, con
responsabilidad exclusiva sobre el canal WhatsApp. No se mezcla lógica
WhatsApp con `vox_bridge` (IVR) ni con `panel` (administración).

La app `whatsapp` es sincrónica (Django WSGI estándar). No requiere
aiohttp ni WebSocket. Los webhooks de Twilio son llamadas HTTP POST
síncronas estándar.

### 2.6. Extensiones de modelo de datos

Aprobadas y completadas:

**A) Captura de ubicación geográfica del cliente:** WhatsAppSession admite
opcionalmente la ubicación geográfica del cliente (latitud, longitud,
dirección formateada). La captura es opcional — nunca obligatoria. La
ubicación puede llegar por WhatsApp (mensaje de localización nativo,
campos Latitude/Longitude en webhook Twilio) o por IVR (DataCaptureSet).

**B) Sección de destino del cliente:** en todo momento debe conocerse a
qué sección desea ser dirigido el cliente, tanto en el canal WhatsApp como
en el IVR. El agente captura esta intención y la registra en la sesión
para permitir el enrutamiento correcto.

**C) Toma de datos por ambos canales:** los modelos de captura de datos
(DataCaptureSet del Hito 3) se integran con el canal WhatsApp, permitiendo
que el chatbot capture los mismos datos estructurados que el IVR. El canal
de captura (voz o WhatsApp) queda registrado.

**D) Grounding con Google Maps:** para consultas que requieran información
geográfica o de ubicación, el chatbot usa Grounding with Google Maps vía
Vertex AI para proporcionar información precisa de rutas, distancias o
puntos de referencia. Se activa cuando el cliente comparte su ubicación o
solicita información geolocalizada.

---

## 3. Modelo de Datos WhatsApp

### 3.1. Modelos en `whatsapp/models.py`

#### WhatsAppSession — Sesión de conversación WhatsApp
```
id                   AutoField (PK)
company              ForeignKey(Company, on_delete=CASCADE)
phone_number         CharField(max_length=20)   # número del usuario E.164
session_start        DateTimeField(auto_now_add=True)
last_message_at      DateTimeField(auto_now=True)
is_active            BooleanField(default=True)
latitude             DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
longitude            DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
location_address     CharField(max_length=500, blank=True)
location_captured_at DateTimeField(null=True, blank=True)
target_section       ForeignKey(Section, null=True, blank=True, on_delete=SET_NULL,
                                related_name='whatsapp_sessions')
```

#### WhatsAppMessage — Mensaje individual
```
id           AutoField (PK)
session      ForeignKey(WhatsAppSession, on_delete=CASCADE)
direction    CharField(choices=[('IN','Entrante'),('OUT','Saliente')])
body         TextField()
message_type CharField(max_length=20, default='text',
                        choices=[('text','Texto'),('location','Ubicación'),
                                 ('media','Media'),('template','Template')])
latitude     DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
longitude    DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
message_sid  CharField(max_length=50, blank=True)
content_sid  CharField(max_length=50, blank=True)
timestamp    DateTimeField(auto_now_add=True)
```

Para mensajes de tipo 'location', el webhook de Twilio proporciona los
campos Latitude y Longitude. Se almacenan en el mensaje y se propagan a la
sesión.

#### WhatsAppTemplate — Template aprobado por Meta
```
id          AutoField (PK)
company     ForeignKey(Company, on_delete=CASCADE)
name        CharField(max_length=200)
content_sid CharField(max_length=50)
category    CharField(choices=[UTILITY, MARKETING, AUTHENTICATION])
language    CharField(max_length=10, default='es')
is_active   BooleanField(default=True)
created_at  DateTimeField(auto_now_add=True)
```

### 3.2. Migraciones aplicadas

- `0001_initial` — modelos base WhatsAppSession, WhatsAppMessage,
  WhatsAppTemplate.
- `0002_whatsappsession_location_target_section_whatsappmessage_type_coords`
  — campos de ubicación, target_section y message_type/coordenadas.

### 3.3. Relación con modelos del Hito 3

Los modelos `WhatsApp*` se integran con la base de datos multiempresa
existente:
- `WhatsAppSession.company` → `ivr_config.Company`
- `WhatsAppSession.target_section` → `ivr_config.Section`
- El chatbot consulta `ivr_config.Section`, `ivr_config.Contact` y
  `ivr_config.PresenceStatus` para construir el contexto del agente.
- El webhook de presencia identifica al CompanyUser por
  `ivr_config.Contact.phone_number` (campo E.164).

---

## 4. Arquitectura de la App `whatsapp`

### 4.1. Estructura de archivos

```
whatsapp/
├── __init__.py
├── apps.py
├── models.py
├── views.py          <- IncomingWhatsAppView + PresenceWhatsAppView
├── urls.py           <- /api/whatsapp/incoming/ + /api/whatsapp/presence/
├── services.py        <- WhatsAppChatService + PresenceResponseService
├── admin.py
├── tasks.py           <- expire_whatsapp_sessions + check_in_meeting_reminders
│                          + expire_presence_statuses
├── migrations/
│   ├── __init__.py
│   ├── 0001_initial.py
│   └── 0002_whatsappsession_location_target_section_whatsappmessage_type_coords.py
└── management/
    └── commands/
        ├── __init__.py
        └── seed_whatsapp_templates.py
```

### 4.2. URLs registradas

```
/api/whatsapp/incoming/   <- POST — webhook mensajes entrantes de usuarios
/api/whatsapp/presence/   <- POST — webhook respuestas de presencia
```

### 4.3. WhatsAppChatService (`whatsapp/services.py`)

- `build_system_prompt(session=None)`: construye el prompt del agente con
  contexto corporativo de Grupo Álvarez, lista de secciones válidas
  inyectada dinámicamente desde BD, bloque de ubicación geográfica cuando
  `session.latitude` no es None, y bloque "DETECCIÓN DE SECCIÓN DESTINO"
  que instruye al agente a añadir el marcador
  `[TARGET_SECTION:{"name": "NOMBRE"}]` al final de su respuesta cuando
  detecte intención inequívoca del cliente.
- `_build_genai_client_maps()`: factory con
  `http_options=HttpOptions(api_version="v1")`, obligatorio para Maps
  Grounding en Vertex AI.
- `_should_use_maps_grounding(session, user_message)`: activa el tool
  cuando `session.latitude` no es None (OR) cuando `user_message` contiene
  keywords geográficos definidos en `GEO_KEYWORDS` (15 términos en
  español).
- `get_gemini_reply(..., session=None)`: rama Maps usa
  `_build_genai_client_maps()` + `Tool(google_maps=GoogleMaps(enable_widget=False))`
  + `ToolConfig(RetrievalConfig(lat_lng=LatLng(...), language_code="es-ES"))`
  cuando `session.latitude` no es None; sin `lat_lng` (activación solo por
  keywords) si es None. Rama estándar sin cambios.
- Imports relevantes: `GoogleMaps`, `HttpOptions`, `LatLng`,
  `RetrievalConfig`, `ToolConfig`, `Q` (de `django.db.models`).

### 4.4. IncomingWhatsAppView (`whatsapp/views.py`)

Flujo por pasos:
- **Step 1**: extracción de Latitude/Longitude del POST de Twilio para
  mensajes de tipo location. Validación tolera mensajes sin body cuando
  hay coordenadas.
- **Step 4**: persistencia con `message_type='location'` y coordenadas en
  WhatsAppMessage.
- **Step 4b**: propagación de coordenadas y `location_captured_at` a
  WhatsAppSession.
- **Step 5**: `session` pasada a `build_system_prompt` para enriquecer
  contexto del agente.
- **Step 7**: `effective_user_message` sintetizado para mensajes de
  ubicación puros. `session` pasada a `get_gemini_reply()`.
- **Step 7b**: regex `_TARGET_SECTION_PATTERN` que extrae el marcador JSON
  de `reply_text`, resuelve `Section` por `name+company+is_active` en BD,
  actualiza `WhatsAppSession.target_section` y elimina el marcador de
  `reply_text` antes de despachar al usuario. El marcador se ignora
  silenciosamente si la sección no existe en BD.
- Imports añadidos: `json`, `re`, `Section`.

### 4.5. Bugs corregidos durante validación E2E

1. `whatsapp/services.py`: `models.Q` no importado → corregido con
   `from django.db.models import Q`.
2. `whatsapp/services.py`: `status.ends_at:%H:%M` con valor `None` en
   STATUS_BUSY_UNTIL → corregido con
   `status.ends_at.strftime('%H:%M') if status.ends_at else 'hora desconocida'`.
3. `whatsapp/tasks.py`: accessor `company_user__contact_profile`
   inexistente → corregido a
   `Contact.objects.get(company_user=company_user, is_internal=True)`.
4. `whatsapp/tasks.py`: `Contact` no importado → añadido a imports de
   `ivr_config.models`.
5. `whatsapp/tasks.py`: modo sandbox para `content_sid` PENDING →
   eliminado en sesión posterior (ver 4.6).

### 4.6. tasks.py — estado final

Bloque condicional `_use_freeform` (modo sandbox para `content_sid`
PENDING) eliminado. Envío puro por `content_sid` consolidado. Templates
sembrados con ContentSid reales (ver Sección 5).

### 4.7. vox_bridge — ForwardToMobileView

Añadido a `vox_bridge/views.py` y su ruta correspondiente en
`vox_bridge/urls.py`: `/api/vox/forward-to-mobile/` (GET y POST,
csrf_exempt, sin validación de firma Twilio). Endpoint creado para el
flujo de verificación Meta, en el que Twilio recibe una llamada de Meta y
la reenvía con `<Dial callerId="+34951799117">+34711509585</Dial>`.

**Nota:** este endpoint quedó sin uso en producción porque el flujo
correcto para números Twilio de voz es Voice→email (OTP llega a
nummenor@gmail.com). Puede eliminarse o reutilizarse en futuros flujos de
reenvío.

---

## 5. Templates WhatsApp

### 5.1. Template de recordatorio de presencia

- Nombre: `presence_reminder`
- Categoría: UTILITY — Idioma: es
- Cuerpo: "¿Sigues reunido? Responde: 1h / 2h / disponible"
- ContentSid en BD: `HXe0ea154a5fa8756be305f6f0c24023c4` — APROBADO (Meta,
  2026-04-10)
- Estado Twilio: WhatsApp user initiated / WhatsApp business initiated
  ambos aprobados.

### 5.2. Template de bienvenida fuera de sesión

- Nombre: `welcome_message`
- Categoría: UTILITY — Idioma: es
- Cuerpo: "Hola {{1}}, soy el asistente virtual de {{2}}. ¿En qué puedo
  ayudarte hoy?"
- ContentSid en BD: `HX6619d4bded96b01c62fada40e6259dd8` — APROBADO (Meta,
  2026-04-10)
- Estado Twilio: WhatsApp user initiated / WhatsApp business initiated
  ambos aprobados.

---

## 6. Modificaciones a Archivos Existentes

### 6.1. `enterprise_core/settings.py`
`whatsapp` en INSTALLED_APPS. CELERY_BEAT_SCHEDULE con las tres tareas
Celery (`expire_whatsapp_sessions`, `check_in_meeting_reminders`,
`expire_presence_statuses`).

### 6.2. `enterprise_core/urls.py`
`path('api/whatsapp/', include('whatsapp.urls'))` registrado.

### 6.3. `.env`
`TWILIO_WHATSAPP_SENDER=+34607961650` (producción — sender registrado y
operativo).

---

## 7. Comandos de Gestión

```bash
python -m dotenv run python manage.py seed_whatsapp_templates
```

### Secuencia de arranque

El canal WhatsApp opera sobre Django WSGI (PythonAnywhere). No requiere
bridge. El IVR requiere `voice_orchestrator.py` activo (always-on task).

---

## 8. Panel: Gestión de Templates WhatsApp

Vistas responsive en el panel personalizado (`/panel/`) para que el ADMIN
gestione sus `WhatsAppTemplate` (listado + detalle solo lectura):

- `WhatsAppTemplateListView` (`AdminRoleRequiredMixin` + `ListView`),
  queryset filtrado por empresa e `is_active=True`.
- Ruta `/panel/whatsapp/templates/` (`name=whatsapp_template_list`).
- Plantilla `template_list.html`: tabla responsive Bootstrap 5.3
  (columnas: Nombre, SID de contenido, Categoría, Idioma, Estado).
- Entrada WhatsApp en sidebar fijo y offcanvas con icono `bi-whatsapp` y
  sección label WHATSAPP.
- Validación E2E superada en escritorio, móvil y offcanvas: URL accesible,
  sidebar con highlight activo, tabla renderizando `presence_reminder` y
  `welcome_message` con ContentSid reales de Grupo Álvarez.

---

## 9. Pendientes Diferidos

**NOTA RESPONSIVE:** la interfaz del panel (`/panel/`) debe ser
completamente responsive. La mayoría de accesos se realizarán desde
dispositivos móviles y tablets. Aplicar en todas las vistas: uso correcto
de `col-12`/`col-md-*`/`col-lg-*`, tablas con `table-responsive`,
formularios con inputs de tamaño adecuado para pantalla táctil,
navegación colapsable en móvil.

1. **Mensajes proactivos (business-initiated):** envío fuera de sesión
   con templates. Se implementará cuando haya un caso de uso real definido
   con Grupo Álvarez.
2. **Mensajes de media** (imágenes, documentos): soporte para adjuntos
   entrantes. Útil para recepción de albaranes o fotos de incidencias.
   Requiere manejo de `MediaUrl0` y `MediaContentType0` en el webhook.
3. **Botones interactivos (Quick Replies):** templates con botones de
   respuesta rápida para flujos predefinidos. Requieren templates de tipo
   `twilio/quick-reply` en el Content Template Builder.
4. **Escalado a llamada de voz:** si el chatbot detecta que la consulta
   requiere atención personal, puede proponer una llamada. Desde finales
   de 2025, Twilio soporta llamadas de voz por WhatsApp. Implementación en
   hito posterior.
5. **Números ES para WhatsApp:** cuando lleguen los números españoles
   aprobados, registrarlos también como senders WhatsApp.
6. **Revisión de roles, grupos y flujos del Hito 3:** diseño del diagrama
   de flujo de Grupo Álvarez, revisión de permisos por rol (ADMIN/STAFF) y
   configuración del enrutamiento IVR por sección según disponibilidad en
   tiempo real.
7. **Arquitectura omnicanal IVR ↔ WhatsApp** (aprobado en sesión
   2026-04-20): tres líneas de trabajo aprobadas para el Hito 5
   (Arquitectura Omnicanal IVR ↔ WhatsApp):
   - Línea A — Panel: entrada WhatsApp en sidebar (cubierta por el panel
     de templates de este hito).
   - Línea B — IVR: persistencia de datos capturados por `DataCaptureSet`
     en BD mediante nuevo modelo `CallDataCapture` vinculado a `Section`,
     `Contact` y `CallFlow`. Los datos capturados por el IVR deben
     persistir en BD y no solo procesarse en tiempo de llamada.
   - Línea C — Puente IVR ↔ WhatsApp: datos capturados por el IVR se
     adjuntan al contacto de sección y se envían vía WhatsApp al agente
     interno antes del transfer de la llamada. Flujo: IVR captura →
     persiste en BD → WhatsApp notifica al contacto con resumen del
     cliente → transfer ejecutado. Esta pieza cierra el ciclo omnicanal
     completo de EnterpriseBot.

---

## 10. Registro de Sesiones

| Sesión | Fecha | Resumen |
|---|---|---|
| S001 | 2026-04-09 | Planificación estratégica. Decisión Twilio for WhatsApp vs Meta Cloud API. Análisis de constelación documental del Hito 3, identificación de dos puntos de integración WhatsApp predefinidos (presencia). |
| S002 | 2026-04-10 | Implementación canal WhatsApp: modelos, app Django completa (models, admin, services, tasks, views, urls), migraciones, seed de templates, PMA sobre settings.py y urls.py. Incorporación de números ES +34951799117 y +34951796832 (capabilities=BOTH). Inicio de registro de sender WhatsApp, bloqueado por exceso de intentos OTP. Pausa para reactivar Hito 3. |
| S003 | 2026-04-13 | Desbloqueo de prerrequisitos externos. Diagnóstico y resolución de fallo de verificación Meta de +34951799117 (flujo Voice→email, OTP a nummenor@gmail.com). ForwardToMobileView en vox_bridge. Sandbox Twilio configurado y conectado. 5 bugs corregidos en services.py y tasks.py. Validación Paso 16 (chatbot, 3 turnos con contexto) y Paso 17 (webhook de presencia, ciclo IN_MEETING→AVAILABLE). Extensiones de modelo aprobadas (ubicación, sección destino, captura por ambos canales, grounding Maps). |
| S004 | 2026-04-16 (1ª) | Reanudación tras cierre del Hito 3. Investigación registro WhatsApp 2026: Twimlets obsoletos, método correcto Twilio Function mínima. Documento satélite V04DOC_WHATSAPP_NUMBER_REGISTRATION.md. Actualización Sección 2.3 y preparación de anexos para inicio formal del Hito 4. |
| S005 | 2026-04-16 (2ª) | Pasos 18 y 19: arquitectura CallFlow por Section (Estrategia B) con fallback_section, migración ivr_config 0007. Extensión WhatsAppSession/WhatsAppMessage con campos de ubicación y tipo de mensaje (migración whatsapp 0002), admin.py actualizado, lógica de detección y propagación de mensajes de ubicación. Investigación Grounding with Google Maps (documentado, no iniciado). Intento de registro de +34951799117 bloqueado por Meta (ambos números OTP bloqueados) — ticket Twilio #26344158 (P2 High). Migración de facturación GCP gen-lang-client-0961484137 a cuenta Grúas Álvarez. Pausa para reactivar Hito 3 (Estrategia B IVR). |
| S006 | 2026-04-20 (1ª) | Actualización Grounding with Google Maps (GA en Vertex AI desde sept. 2025, api_version="v1" obligatorio). Paso 20: _build_genai_client_maps(), _should_use_maps_grounding(), rama Maps Grounding en get_gemini_reply(). Paso 21: detección de sección destino, marcador [TARGET_SECTION:{...}], Step 7b en IncomingWhatsAppView con resolución de Section en BD. Confirmación de que +34607961650 quedó registrado y operativo durante el fin de semana (ticket #26344158 resuelto). Pasos 22 y 23: eliminación de lógica sandbox de tasks.py, seed de ContentSid reales (presence_reminder, welcome_message), sembrado de PhoneNumber +34607961650 en BD, actualización de TWILIO_WHATSAPP_SENDER. Validación E2E del canal de producción superada. Aprobación de arquitectura omnicanal IVR↔WhatsApp (Líneas A/B/C) para hito posterior. |
| S007 | 2026-04-20 (2ª) | Paso 24: panel de gestión de templates WhatsApp. WhatsAppTemplateListView (AdminRoleRequiredMixin + ListView, filtrado por empresa e is_active=True), ruta /panel/whatsapp/templates/, plantilla template_list.html con tabla responsive Bootstrap 5.3, entrada WhatsApp en sidebar fijo y offcanvas (icono bi-whatsapp, sección label WHATSAPP). Validación E2E en escritorio, móvil y offcanvas superada con ContentSid reales. Hito 4 completado. Aprobación de creación del Hito 5 (Arquitectura Omnicanal IVR↔WhatsApp), hito híbrido de los Hitos 3 y 4, cubriendo Líneas A (panel), B (persistencia CallDataCapture) y C (notificación WhatsApp al agente antes del transfer IVR). |

---

## 11. Hoja de Ruta para la Siguiente Sesion

### Criterios de reapertura

Este hito puede reabrirse para:

1. **Mensajes proactivos** (business-initiated) cuando exista un caso de
   uso real definido con Grupo Álvarez.
2. **Mensajes de media** (imágenes, documentos) — soporte MediaUrl0/
   MediaContentType0 en el webhook.
3. **Botones interactivos (Quick Replies)** vía templates
   `twilio/quick-reply`.
4. **Escalado a llamada de voz** desde WhatsApp (disponible en Twilio
   desde finales de 2025).
5. **Números ES para WhatsApp** cuando lleguen aprobados.
6. **Regresión** en el chatbot, el sistema de presencia o las
   integraciones de grounding/sección destino.

El trabajo de continuidad inmediata (arquitectura omnicanal IVR↔WhatsApp,
Líneas A/B/C aprobadas en S006/S007) se desarrolla en el **Hito 5**
(`enterprisebot-annex-v05`), no en este anexo.
