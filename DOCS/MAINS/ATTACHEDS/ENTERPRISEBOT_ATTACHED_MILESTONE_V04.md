# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V04.md

# ENTERPRISEBOT — ANEXO HITO V04 — CANAL WHATSAPP: CHATBOT CONVERSACIONAL Y SISTEMA DE PRESENCIA
**Estado:** EN PROGRESO
**Fecha de inicio:** 2026-04-09
**Fecha de reanudación:** 2026-04-20
**Última actualización:** 2026-04-20
**Prerequisito:** Hito 3 COMPLETADO ✅ (2026-04-16).

---

## SECCIÓN 1 — VISIÓN DEL HITO

Este hito incorpora WhatsApp como canal de comunicación bidireccional en EnterpriseBot,
construido íntegramente sobre la infraestructura Twilio ya existente. Opera en dos
dimensiones complementarias:

**Dimensión 1 — Cierre del bucle de presencia del Hito 3:**
El sistema de presencia diseñado en el Hito 3 quedó con dos piezas pendientes
explícitamente diferidas a este hito: el webhook de respuesta a recordatorios en
/api/whatsapp/presence/ y las tareas Celery check_in_meeting_reminders y
expire_presence_statuses. Este hito las implementa y valida completamente,
cerrando el sistema de presencia de extremo a extremo.

**Dimensión 2 — Chatbot de atención al cliente por WhatsApp:**
Un agente conversacional inteligente, impulsado por Gemini (modelo de texto,
no Live), que atiende consultas entrantes de clientes por WhatsApp. El agente
conoce la estructura de la empresa (secciones, contactos, disponibilidad en
tiempo real por PresenceStatus) y puede informar, derivar y capturar datos,
todo desde la misma base de datos multiempresa construida en el Hito 3.

La empresa piloto es **Grupo Álvarez** (Grúas Álvarez), con la que se refinará
la configuración del agente en sesiones posteriores.

---

## SECCIÓN 2 — DECISIONES ARQUITECTÓNICAS Y TECNOLÓGICAS

### 2.1. Plataforma: Twilio for WhatsApp

**Decisión tomada en sesión 2026-04-09.** Se descartó la integración directa
con Meta Cloud API. Fundamentos:

- El SDK twilio 9.10.4 ya está instalado en EnterpriseBot_venv.
- Las credenciales (TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID,
  TWILIO_API_KEY_SECRET) ya están configuradas en el entorno.
- El patrón webhook/TwiML/Django ya está dominado desde el IVR.
- El Sandbox de Twilio para WhatsApp permite desarrollar y probar sin necesidad
  de verificación Meta Business completa, acelerando el desarrollo.
- Sinergia futura: desde finales de 2025, Twilio soporta llamadas de voz por
  WhatsApp, abriendo la posibilidad de escalar de chat a llamada en el mismo
  hilo en un hito posterior.
- Coste del sobrecargo Twilio ($0.005/mensaje) irrelevante al volumen de
  operación de Grupo Álvarez.

### 2.2. Modelo de IA para el chatbot de texto

**Modelo:** gemini-2.5-flash (Vertex AI) vía google-genai 1.69.0.

**Fundamento:** El canal WhatsApp es texto puro, no audio en tiempo real. No se
usa el modelo Live (gemini-live-2.5-flash-native-audio) porque:
- El modelo Live está diseñado para sesiones de audio A2A en tiempo real con
  WebSocket persistente. Ese patrón es incompatible con la naturaleza stateless
  de los webhooks de WhatsApp.
- gemini-2.5-flash es el modelo de texto de referencia en la plataforma
  Vertex AI, más eficiente y económico para generación de texto conversacional.

**API utilizada:** client.chats.create() / chat.send_message() del SDK
google-genai. La sesión de chat se gestiona de forma manual en BD (modelo
WhatsAppSession), reconstruyendo el historial en cada llamada al webhook.

**Autenticación:** Vertex AI vía Service Account JSON, idéntico al IVR.
Variables de entorno: GCP_CREDENTIALS_PATH, GOOGLE_CLOUD_PROJECT,
GOOGLE_CLOUD_LOCATION.

### 2.3. Gestión de números de Grupo Álvarez en Twilio

**Estado sesión 2026-04-20 (PRODUCCIÓN ACTIVA):**

- **+34607961650** — WhatsApp sender principal. ✅ REGISTRADO Y OPERATIVO.
  Sender status: Online. Throughput: 80 MPS.
  WhatsApp Business Account ID: 950408527754677.
  Meta Business Manager ID: 2762307714126800.
  Webhook configurado: https://enterprisebot-miguelaetxio.pythonanywhere.com/api/whatsapp/incoming/
  Sembrado en BD: pk=5, capabilities=BOTH, is_active=True.
  Variable de entorno: TWILIO_WHATSAPP_SENDER=+34607961650 (en .env).
  Verificación E2E superada: sesión creada en BD, chatbot responde con coherencia
  corporativa de Grupo Álvarez desde número de producción.

  **Historial del proceso de registro:**
  Los Twimlets (`twimlets.com/voicemail`) están marcados como obsoletos en 2026.
  El método correcto utilizado fue una **Twilio Function** mínima durante la
  verificación Meta (10-15 min). Twilio Function desplegada:
  `whatsapp-verify-4871.twil.io/whatsapp-verify`.
  Ticket de soporte Twilio #26344158 (P2 High, 2026-04-16) para reset del
  contador OTP en +34951799117 — resuelto durante el fin de semana del 19-20 de abril.
  Ver documento satélite: `DOCS_ATTACHED_2_ANNEX_V04/V04DOC_WHATSAPP_NUMBER_REGISTRATION.md`

- **+34951799117** — Reservado para IVR de voz.
  Voice Configuration IE1: gestionada por voice_orchestrator.py al arrancar.

- **+34951796832** — Reservado para pruebas IVR de voz.
  Voice Configuration IE1: apunta a ngrok (gestionado por orchestrator).

- **+14155238886** — Sandbox Twilio (desarrollo). Sembrado en BD, capabilities=BOTH.
  Código de unión Sandbox: join kept-title.

**Fase de producción WhatsApp:** sender +34607961650 operativo.
**Nota crítica:** Las plantillas se gestionan exclusivamente a través del
Content Template Builder del Console de Twilio o la Content API. Los templates
tienen SID con prefijo HX y se envían vía el parámetro ContentSid en la API
de mensajería.

### 2.4. Ventana de sesión de 24 horas (regla Meta)

Desde julio de 2025, Meta aplica un modelo de precios por mensaje. Las reglas
de sesión son:

- Mensajes de sesión (ventana 24h): Cuando un usuario envía un mensaje a la
  empresa, se abre una ventana de 24 horas desde el último mensaje recibido.
  Durante esta ventana se pueden enviar mensajes de texto libre sin template,
  sin coste de template Meta (solo el fee Twilio de $0.005/mensaje).
- Mensajes fuera de sesión (business-initiated): Requieren template aprobado
  por Meta. Se envían con ContentSid=HX... Se aplica el fee de template Meta
  según categoría (marketing, utilidad, autenticación).
- Templates de utilidad dentro de la ventana: Gratuitos (fee Meta = $0).
- Templates de utilidad fuera de la ventana: Tienen coste Meta.
- Mensajes de recordatorio de presencia: Se envían como templates de utilidad
  (UTILITY). Deben estar pre-aprobados por Meta antes de su uso en producción.

### 2.5. Arquitectura de la app Django whatsapp

Se crea una nueva app Django whatsapp dentro del proyecto EnterpriseBot,
con responsabilidad exclusiva sobre el canal WhatsApp. No se mezcla lógica
WhatsApp con vox_bridge (IVR) ni con panel (administración).

La app whatsapp es sincrónica (Django WSGI estándar). No requiere aiohttp
ni WebSocket. Los webhooks de Twilio son llamadas HTTP POST síncronas estándar.

### 2.6. Extensiones de modelo de datos aprobadas en sesión 2026-04-13

Se aprueba la extensión del modelo de datos para soportar:

**A) Captura de ubicación geográfica del cliente:**
El modelo WhatsAppSession debe admitir opcionalmente la ubicación geográfica
del cliente (latitud, longitud, dirección formateada). La captura es opcional
— nunca obligatoria. La ubicación puede llegar por WhatsApp (mensaje de
localización nativo de WhatsApp, campos Latitude/Longitude en webhook Twilio)
o por IVR (captura de datos DataCaptureSet). El modelo debe permitir guardar
estos datos sin forzar su captura.

**B) Sección de destino del cliente:**
En todo momento debe conocerse a qué sección desea ser dirigido el cliente,
tanto en el canal WhatsApp como en el IVR. El agente debe capturar esta
intención y registrarla en la sesión para permitir el enrutamiento correcto.

**C) Toma de datos por ambos canales:**
Los modelos de captura de datos (DataCaptureSet del Hito 3) deben integrarse
con el canal WhatsApp, permitiendo que el chatbot capture los mismos datos
estructurados que el IVR. El canal de captura (voz o WhatsApp) queda registrado.

**D) Grounding con Google Maps:**
Para consultas que requieran información geográfica o de ubicación, el chatbot
puede usar Grounding with Google Maps vía Vertex AI para proporcionar
información precisa de rutas, distancias o puntos de referencia. Se activa
cuando el cliente comparte su ubicación o solicita información geolocalizada.

---

## SECCIÓN 3 — MODELO DE DATOS WHATSAPP

### 3.1. Modelos actuales en whatsapp/models.py (implementados — estado 2026-04-16)

#### WhatsAppSession — Sesión de conversación WhatsApp
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
    target_section       ForeignKey(Section, null=True, blank=True, on_delete=SET_NULL)

#### WhatsAppMessage — Mensaje individual
    id           AutoField (PK)
    session      ForeignKey(WhatsAppSession, on_delete=CASCADE)
    direction    CharField(choices=[('IN','Entrante'),('OUT','Saliente')])
    body         TextField()
    message_type CharField(max_length=20, default='text', choices=[text/location/media/template])
    latitude     DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude    DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    message_sid  CharField(max_length=50, blank=True)
    content_sid  CharField(max_length=50, blank=True)
    timestamp    DateTimeField(auto_now_add=True)

#### WhatsAppTemplate — Template aprobado por Meta
    id          AutoField (PK)
    company     ForeignKey(Company, on_delete=CASCADE)
    name        CharField(max_length=200)
    content_sid CharField(max_length=50)
    category    CharField(choices=[UTILITY, MARKETING, AUTHENTICATION])
    language    CharField(max_length=10, default='es')
    is_active   BooleanField(default=True)
    created_at  DateTimeField(auto_now_add=True)

### 3.2. Extensiones de modelo implementadas en sesión 2026-04-16 (Paso 18) ✅

#### Extensión WhatsAppSession — campos de ubicación y sección destino
Los siguientes campos deben añadirse mediante migración:

    latitude            DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude           DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_address    CharField(max_length=500, blank=True)  # dirección formateada
    location_captured_at DateTimeField(null=True, blank=True)  # cuándo se capturó
    target_section      ForeignKey(Section, null=True, blank=True, on_delete=SET_NULL,
                                   related_name='whatsapp_sessions')  # sección de destino

Reglas:
- Todos los campos de ubicación son opcionales (null=True, blank=True).
- target_section se actualiza cuando el agente detecta la intención de sección.
- location_captured_at registra el momento de captura para auditoría.

#### Extensión WhatsAppMessage — tipo de mensaje
    message_type        CharField(max_length=20, default='text',
                                  choices=[('text','Texto'),('location','Ubicación'),
                                           ('media','Media'),('template','Template')])
    latitude            DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude           DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

Para mensajes de tipo 'location', el webhook de Twilio proporciona los campos
Latitude y Longitude. Se almacenan en el mensaje y se propagan a la sesión.

### 3.3. Relación con modelos del Hito 3

Los modelos WhatsApp* se integran con la base de datos multiempresa existente:
- WhatsAppSession.company → ivr_config.Company
- WhatsAppSession.target_section → ivr_config.Section
- El chatbot consulta ivr_config.Section, ivr_config.Contact y
  ivr_config.PresenceStatus para construir el contexto del agente.
- El webhook de presencia identifica al CompanyUser por
  ivr_config.Contact.phone_number (campo E.164).

---

## SECCIÓN 4 — ARQUITECTURA DE LA APP whatsapp

### 4.1. Estructura de archivos (estado actual)

    whatsapp/
    ├── __init__.py
    ├── apps.py
    ├── models.py
    ├── views.py          <- IncomingWhatsAppView + PresenceWhatsAppView
    ├── urls.py           <- /api/whatsapp/incoming/ + /api/whatsapp/presence/
    ├── services.py       <- WhatsAppChatService + PresenceResponseService
    ├── admin.py
    ├── tasks.py          <- expire_whatsapp_sessions + check_in_meeting_reminders
    │                        + expire_presence_statuses
    ├── migrations/
    │   ├── __init__.py
    │   ├── 0001_initial.py
    │   └── 0002_whatsappsession_location_target_section_whatsappmessage_type_coords.py
    └── management/
        └── commands/
            ├── __init__.py
            └── seed_whatsapp_templates.py

### 4.2. URLs registradas

    /api/whatsapp/incoming/   <- POST — webhook mensajes entrantes de usuarios
    /api/whatsapp/presence/   <- POST — webhook respuestas de presencia

### 4.3. Bugs corregidos en sesión 2026-04-13

Los siguientes bugs fueron detectados y corregidos durante la validación E2E:

1. whatsapp/services.py: `models.Q` no importado → corregido con
   `from django.db.models import Q`. Uso actualizado a `Q(...)` directo.
2. whatsapp/services.py: `status.ends_at:%H:%M` con valor None en STATUS_BUSY_UNTIL
   → corregido con `status.ends_at.strftime('%H:%M') if status.ends_at else 'hora desconocida'`.
3. whatsapp/tasks.py: accessor `company_user__contact_profile` inexistente
   → corregido a `Contact.objects.get(company_user=company_user, is_internal=True)`.
4. whatsapp/tasks.py: `Contact` no importado → añadido a imports de ivr_config.models.
5. whatsapp/tasks.py: modo sandbox para content_sid PENDING → lógica condicional
   `_use_freeform = template.content_sid.startswith("PENDING_")` añadida.
   NOTA: esta lógica debe eliminarse cuando los ContentSid reales estén sembrados.

### 4.4. vox_bridge — añadidos en sesión 2026-04-13

Se añadió ForwardToMobileView a vox_bridge/views.py y su ruta correspondiente
en vox_bridge/urls.py: /api/vox/forward-to-mobile/ (GET y POST, csrf_exempt,
sin validación de firma Twilio). Endpoint creado para el flujo de verificación
Meta, en el que Twilio recibe una llamada de Meta y la reenvía con
<Dial callerId="+34951799117">+34711509585</Dial>.
NOTA: este endpoint quedó sin uso en producción porque el flujo correcto para
números Twilio de voz es Voice→email (OTP llega a nummenor@gmail.com).
Puede eliminarse o reutilizarse en futuros flujos de reenvío.

---

## SECCIÓN 5 — TEMPLATES WHATSAPP REQUERIDOS

### 5.1. Template de recordatorio de presencia

Nombre: presence_reminder
Categoría: UTILITY — Idioma: es
Cuerpo: ¿Sigues reunido? Responde: 1h / 2h / disponible
ContentSid en BD: HXe0ea154a5fa8756be305f6f0c24023c4 ✅ APROBADO (Meta, 2026-04-10)
Estado Twilio: WhatsApp user initiated ✅ / WhatsApp business initiated ✅

### 5.2. Template de bienvenida fuera de sesión

Nombre: welcome_message
Categoría: UTILITY — Idioma: es
Cuerpo: Hola {{1}}, soy el asistente virtual de {{2}}. ¿En qué puedo ayudarte hoy?
ContentSid en BD: HX6619d4bded96b01c62fada40e6259dd8 ✅ APROBADO (Meta, 2026-04-10)
Estado Twilio: WhatsApp user initiated ✅ / WhatsApp business initiated ✅

---

## SECCIÓN 6 — MODIFICACIONES A ARCHIVOS EXISTENTES (completadas)

### 6.1. enterprise_core/settings.py ✅
whatsapp en INSTALLED_APPS. CELERY_BEAT_SCHEDULE con las tres tareas Celery.

### 6.2. enterprise_core/urls.py ✅
path('api/whatsapp/', include('whatsapp.urls')) registrado.

### 6.3. .env ✅
TWILIO_WHATSAPP_SENDER=+34607961650 (Producción — sender registrado y operativo).

---

## SECCIÓN 7 — COMANDOS DE GESTIÓN

### Comando: seed_whatsapp_templates
    python -m dotenv run python manage.py seed_whatsapp_templates

### Secuencia de arranque
El canal WhatsApp opera sobre Django WSGI (PythonAnywhere). No requiere bridge.
El IVR requiere voice_orchestrator.py activo (always-on task).

---

## SECCIÓN 8 — HOJA DE RUTA

### Paso 1 — Verificación Meta de +34607961650 ✅ COMPLETADO (fin de semana 2026-04-19/20)
Sender registrado y operativo. Ver Sección 2.3 para detalles completos.
Número definitivo: +34607961650 (distinto al planificado inicialmente +34951799117).
Ticket #26344158 resuelto por Twilio/Meta durante el fin de semana.

### Paso 2 — Sandbox ✅ COMPLETADO
Teléfono +34688360595 conectado con código join kept-title.
Webhook configurado en Sandbox settings.

### Pasos 3–15 ✅ COMPLETADOS
Ver historial de sesiones en Sección 10.

### Paso 16 — Validación E2E chatbot de texto ✅ COMPLETADO (sesión 2026-04-13)
3 turnos con contexto persistente validados. Agente responde con coherencia
corporativa de Grupo Álvarez. WhatsAppSession y WhatsAppMessage creados en BD.

### Paso 17 — Validación E2E webhook de presencia ✅ COMPLETADO (sesión 2026-04-13)
Ciclo completo validado: IN_MEETING → recordatorio enviado → respuesta 'disponible'
→ AVAILABLE creado en BD sin intervención manual.

### Paso 18 — Extensión del modelo de datos ✅ COMPLETADO (sesión 2026-04-16)
Campos de ubicación y sección destino añadidos a WhatsAppSession y WhatsAppMessage.
Migración 0002 aplicada sin errores. admin.py actualizado para exponer todos los
nuevos campos. Ver Sección 3.1 para el modelo de datos actualizado.

### Paso 19 — Integración de captura de ubicación en el chatbot ✅ COMPLETADO (sesión 2026-04-16)
IncomingWhatsAppView actualizado para detectar mensajes de tipo location:
- Extracción de Latitude/Longitude del POST de Twilio en Step 1.
- Guarda de validación actualizada para tolerar mensajes sin body cuando hay coordenadas.
- Step 4: persistencia con message_type='location' y coordenadas en WhatsAppMessage.
- Step 4b: propagación de coordenadas y location_captured_at a WhatsAppSession.
- Step 5: session pasada a build_system_prompt para enriquecer contexto del agente.
- Step 7: effective_user_message sintetizado para mensajes de ubicación puros.
WhatsAppChatService.build_system_prompt acepta session opcional e inyecta bloque
de ubicación geográfica cuando session.latitude no es None.

### Paso 20 — Grounding con Google Maps ✅ COMPLETADO (sesión 2026-04-20)
Implementado en WhatsAppChatService (whatsapp/services.py):
- Nueva factory _build_genai_client_maps() con http_options=HttpOptions(api_version="v1"),
  obligatorio para Maps Grounding en Vertex AI.
- Nuevo método _should_use_maps_grounding(session, user_message): activa el tool
  cuando session.latitude no es None (OR) cuando user_message contiene keywords
  geográficos definidos en GEO_KEYWORDS (15 términos en español).
- get_gemini_reply() ampliado con parámetro session=None. Rama Maps: cliente
  _build_genai_client_maps() + Tool(google_maps=GoogleMaps(enable_widget=False))
  + ToolConfig(RetrievalConfig(lat_lng=LatLng(...), language_code="es-ES")).
  Cuando session.latitude es None, ToolConfig sin lat_lng (activación solo por keywords).
  Rama estándar: sin cambios respecto a implementación anterior.
- Imports añadidos: GoogleMaps, HttpOptions, LatLng, RetrievalConfig, ToolConfig.
- views.py actualizado: session pasada a get_gemini_reply() en Step 7 (Paso 20).

### Paso 21 — Detección y registro de sección destino ✅ COMPLETADO (sesión 2026-04-20)
Implementado en whatsapp/services.py y whatsapp/views.py:
- build_system_prompt() ampliado con bloque "DETECCIÓN DE SECCIÓN DESTINO": instruye
  al agente a añadir marcador [TARGET_SECTION:{"name": "NOMBRE"}] al final de su
  respuesta cuando detecte intención inequívoca del cliente. Lista de secciones
  válidas inyectada dinámicamente desde BD para evitar alucinaciones.
- IncomingWhatsAppView: nuevo Step 7b con regex _TARGET_SECTION_PATTERN que:
  1. Extrae el marcador JSON de reply_text.
  2. Resuelve Section por name+company+is_active en BD.
  3. Actualiza WhatsAppSession.target_section.
  4. Elimina el marcador de reply_text antes de despachar al usuario.
  El marcador se ignora silenciosamente si la sección no existe en BD.
- Imports añadidos a views.py: json, re, Section.

### Paso 22 — Eliminación de lógica sandbox de tasks.py ✅ COMPLETADO (sesión 2026-04-20)
Bloque condicional _use_freeform eliminado de check_in_meeting_reminders.
Envío puro por content_sid consolidado. Templates sembrados con ContentSid reales:
- presence_reminder: HXe0ea154a5fa8756be305f6f0c24023c4
- welcome_message: HX6619d4bded96b01c62fada40e6259dd8

### Paso 23 — Habilitación del número de producción para WhatsApp ✅ COMPLETADO (sesión 2026-04-20)
- PhoneNumber +34607961650 sembrado en BD: pk=5, capabilities=BOTH, is_active=True.
- TWILIO_WHATSAPP_SENDER actualizado en .env a +34607961650.
- Webhook entrante configurado en Twilio Console sender +34607961650.
- Validación E2E superada: sesión BD creada, chatbot responde correctamente.

### Paso 24 — Panel: gestión de templates WhatsApp ⏳ PENDIENTE (próxima sesión)
Añadir al panel personalizado (/panel/) vistas responsive para que el ADMIN
gestione sus WhatsAppTemplate (listado + detalle solo lectura).
La interfaz del panel debe ser completamente responsive (Bootstrap 5.3
breakpoints móvil/tablet/escritorio). Ver Hoja de Ruta para la Siguiente Sesión
y nota en Sección 9.

---

## SECCIÓN 8B — HOJA DE RUTA PARA LA SIGUIENTE SESIÓN

### Objetivo de la sesión
Implementar el **Paso 24**: panel de gestión de templates WhatsApp integrado
en el panel personalizado existente (/panel/) de EnterpriseBot.

### Contexto técnico obligatorio
- El panel existente usa Bootstrap 5.3, herencia de `panel/templates/panel/base.html`
  y vistas basadas en clases Django (CBV). Todas las vistas nuevas deben seguir
  exactamente el mismo patrón estructural que las vistas existentes en `panel/views.py`.
- La sidebar de navegación está en `panel/templates/panel/base.html`. Debe añadirse
  una nueva entrada "WhatsApp" con icono apropiado, enlazando a la vista de listado
  de templates.
- Responsive obligatorio: col-12/col-md-*/col-lg-*, tablas con table-responsive,
  inputs táctiles, navegación colapsable en móvil.

### Archivos a solicitar al inicio de la sesión
Solicitar en file01.txt (concatenados):
- panel/templates/panel/base.html (estructura de sidebar y navegación)
- panel/views.py (patrón de CBV existente)
- panel/urls.py (patrón de rutas existente)
- panel/mixins.py (mixins de autenticación/autorización)
- whatsapp/models.py (modelo WhatsAppTemplate para referencia)

### Implementación requerida — archivos nuevos (PEA)
1. panel/templates/panel/whatsapp/template_list.html
   - Tabla responsive con columnas: Nombre, ContentSid, Categoría, Idioma, Estado.
   - Fila por cada WhatsAppTemplate activo de la empresa del usuario.
   - Sin acciones de edición ni borrado — solo lectura.
   - Breadcrumb: Panel > WhatsApp > Plantillas.

### Implementación requerida — archivos sensibles (PMA)
1. panel/views.py — añadir WhatsAppTemplateListView (LoginRequiredMixin,
   CompanyFilterMixin o equivalente). QuerySet: WhatsAppTemplate.objects.filter(
   company=request.user.companyuser.company, is_active=True).order_by('name').
2. panel/urls.py — añadir path('whatsapp/templates/', WhatsAppTemplateListView,
   name='whatsapp_template_list').
3. panel/templates/panel/base.html — añadir entrada sidebar WhatsApp con enlace
   a whatsapp_template_list. Icono sugerido: Bootstrap Icons bi-whatsapp o similar.

### Criterio de éxito
- Vista accesible desde /panel/whatsapp/templates/ sin errores.
- Sidebar muestra la entrada WhatsApp activa con highlight correcto en la página.
- Tabla renderiza los dos WhatsAppTemplate de Grupo Álvarez con sus ContentSid reales.
- Layout completamente responsive en móvil, tablet y escritorio.

---

## SECCIÓN 9 — PENDIENTES DIFERIDOS

**NOTA RESPONSIVE:** La interfaz del panel (/panel/) debe ser completamente
responsive. La mayoría de accesos se realizarán desde dispositivos móviles y
tablets. Aplicar en todas las vistas: uso correcto de col-12/col-md-*/col-lg-*,
tablas con table-responsive, formularios con inputs de tamaño adecuado para
pantalla táctil, navegación colapsable en móvil.

1. Mensajes proactivos (business-initiated): Envío fuera de sesión con templates.
   Se implementará cuando haya un caso de uso real definido con Grupo Álvarez.

2. Mensajes de media (imágenes, documentos): Soporte para adjuntos entrantes.
   Útil para recepción de albaranes o fotos de incidencias. Requiere manejo
   de MediaUrl0 y MediaContentType0 en el webhook.

3. Botones interactivos (Quick Replies): Templates con botones de respuesta
   rápida para flujos predefinidos. Requieren templates de tipo twilio/quick-reply
   en el Content Template Builder.

4. Escalado a llamada de voz: Si el chatbot detecta que la consulta requiere
   atención personal, puede proponer una llamada. Desde finales de 2025, Twilio
   soporta llamadas de voz por WhatsApp. Se implementará en un hito posterior.

5. Números ES para WhatsApp: Cuando lleguen los números españoles aprobados,
   registrarlos también como senders WhatsApp.

6. Revisión de roles, grupos y flujos del Hito 3: Pendiente de reactivación
   del Hito 3. Incluye diseño del diagrama de flujo de Grupo Álvarez, revisión
   de permisos por rol (ADMIN/STAFF) y configuración del enrutamiento IVR
   por sección según disponibilidad en tiempo real.

7. Arquitectura omnicanal IVR ↔ WhatsApp (aprobado en sesión 2026-04-20):
   Tres líneas de trabajo aprobadas para un hito posterior (Hito 5 o ampliación
   del Hito 3):
   - Línea A — Panel: entrada WhatsApp en sidebar (cubierta por Paso 24).
   - Línea B — IVR: persistencia de datos capturados por DataCaptureSet en BD
     mediante nuevo modelo CallDataCapture vinculado a Section, Contact y CallFlow.
     Los datos capturados por el IVR deben persistir en BD y no solo procesarse
     en tiempo de llamada.
   - Línea C — Puente IVR ↔ WhatsApp: datos capturados por el IVR se adjuntan
     al contacto de sección y se envían vía WhatsApp al agente interno antes del
     transfer de la llamada. Flujo: IVR captura → persiste en BD →
     WhatsApp notifica al contacto con resumen del cliente → transfer ejecutado.
     Esta pieza cierra el ciclo omnicanal completo de EnterpriseBot.

---

## SECCIÓN 10 — PAH — REGISTRO DE SESIONES

### Sesión 2026-04-20
**Título:** Hito 4 — Grounding Google Maps, Detección de Sección Destino y Producción WhatsApp
**Descripción:** Sesión de reanudación del Hito 4 tras pausa de la sesión 2026-04-16. Se ejecuta
la actualización en línea obligatoria de la API Grounding with Google Maps en Vertex AI (GA desde
sept. 2025, confirmado api_version="v1" obligatorio). Se implementa el Paso 20: nueva factory
_build_genai_client_maps(), método _should_use_maps_grounding() con activación dual por coordenadas
y keywords geográficos, y rama Maps Grounding en get_gemini_reply() con ToolConfig/RetrievalConfig/
LatLng/language_code="es-ES". Se implementa el Paso 21: instrucción de detección de sección destino
en build_system_prompt() con marcador [TARGET_SECTION:{...}] y Step 7b en IncomingWhatsAppView con
parsing regex, resolución de Section en BD y limpieza del marcador. Se constata que el sender
+34607961650 quedó registrado y operativo durante el fin de semana (ticket #26344158 resuelto).
Se completan los Pasos 22 y 23: eliminación de lógica sandbox en tasks.py, seed con ContentSid
reales (presence_reminder: HXe0ea154a5fa8756be305f6f0c24023c4, welcome_message:
HX6619d4bded96b01c62fada40e6259dd8), sembrado de PhoneNumber +34607961650 en BD y actualización
de TWILIO_WHATSAPP_SENDER en .env. Validación E2E del canal de producción superada. Se aprueba
arquitectura omnicanal IVR ↔ WhatsApp (Líneas A/B/C) para hito posterior.

### Sesión 2026-04-16 (segunda entrada)
**Título:** Hito 4 — Extensión del Modelo de Datos, Captura de Ubicación y Gestión de Facturación GCP
**Descripción:** Sesión dedicada a la implementación de los Pasos 18 y 19 del Hito 4 y a la gestión
administrativa de la plataforma. Se diseña y aprueba la arquitectura de CallFlow por Section
(Estrategia B — carga dinámica por intención) con fallback_section por número, extendiendo los
modelos ivr_config con Section.call_flow y CallFlow.fallback_section (migración 0007 aplicada).
Se implementan los Pasos 18 y 19: extensión de WhatsAppSession y WhatsAppMessage con campos de
ubicación y tipo de mensaje (migración 0002 aplicada), actualización de admin.py de ambas apps,
y lógica completa de detección y propagación de mensajes de ubicación en views.py y services.py.
Se investiga Grounding with Google Maps (GA en Vertex AI desde sept. 2025) — queda documentado
pero no iniciado. Se intenta el registro del número +34951799117 como WhatsApp sender — Meta
bloquea el contador OTP en ambos números (+34951799117 y +34951796832). Se abre ticket de
soporte con Twilio (#26344158, P2 High) para escalado a Meta. Se migra la facturación del
proyecto GCP gen-lang-client-0961484137 de cuenta_pago_el_campus a la nueva cuenta Grúas
Álvarez. El hito se pausa para reactivar el Hito 3 (Estrategia B IVR).

### Sesión 2026-04-16 (primera entrada)
**Título:** Reanudación Hito 4 — Investigación Registro WhatsApp y Apertura de Hito
**Descripción:** Sesión de reanudación del Hito 4 tras cierre del Hito 3. Se investiga
el estado actual del registro de números Twilio para WhatsApp en 2026, detectando
que los Twimlets están obsoletos y el método correcto es una Twilio Function mínima
con desactivación temporal del IVR durante la verificación Meta. Se genera el
documento satélite V04DOC_WHATSAPP_NUMBER_REGISTRATION.md con el análisis completo,
viabilidad confirmada y procedimiento paso a paso. Se actualiza el procedimiento en
la Sección 2.3 del presente anexo. Se preparan ambos anexos y el Master Document
para el inicio formal del Hito 4.

### Sesión 2026-04-13
**Título:** Hito 4 — Verificación Meta, Sandbox WhatsApp y Validación E2E del Chatbot
**Descripción:** Sesión dedicada a desbloquear los prerrequisitos externos del
Hito 4 y ejecutar las validaciones E2E pendientes. Se diagnostica y resuelve el
fallo de verificación Meta del número +34951799117 (flujo correcto: Voice→email,
OTP a nummenor@gmail.com). Se implementa ForwardToMobileView en vox_bridge para
reenvío de llamadas. Se configura el Sandbox de Twilio y se conecta el teléfono
de prueba. Se corrigen 5 bugs en whatsapp/services.py y whatsapp/tasks.py
detectados durante la validación. Se valida el Paso 16 (chatbot, 3 turnos con
contexto) y el Paso 17 (webhook de presencia, ciclo completo IN_MEETING→AVAILABLE).
Se aprueban extensiones de modelo para ubicación geográfica, sección destino,
captura de datos por ambos canales y grounding con Google Maps.

### Sesión 2026-04-10
**Título:** Hito 4 — Implementación Canal WhatsApp: Modelos, App Django y Flujos Base
**Descripción:** Sesión de implementación del canal WhatsApp. Se incorporan los
números ES +34951799117 y +34951796832 (geográficos Málaga, capabilities=BOTH)
sustituyendo el número US eliminado. Se añade el campo capabilities al modelo
PhoneNumber con migración. Se implementan todos los archivos de la app whatsapp
(models, admin, services, tasks, views, urls), las migraciones, el seed de
templates y los PMA sobre settings.py y urls.py. Se inicia el proceso de
registro del sender WhatsApp en Twilio/Meta para +34951799117, quedando
bloqueado temporalmente por exceso de intentos de verificación. El hito se
pausa para reactivar el Hito 3 y probar el IVR con los nuevos números ES.

### Sesión 2026-04-09
**Título:** Cambio Estratégico: Diseño del Hito 4 — Chatbot WhatsApp sobre Twilio
**Descripción:** Sesión de planificación estratégica. Se decide aprovechar la
espera de los números españoles para desarrollar el canal WhatsApp. Se realiza
investigación en línea comparativa entre Twilio for WhatsApp y Meta Cloud API
directa, concluyendo con Twilio como plataforma por reutilización total de
infraestructura, SDK ya instalado y sinergia con el IVR. Se analiza la
constelación documental del Hito 3, identificando dos puntos de integración
WhatsApp ya predefinidos en el sistema de presencia. Se establece que el Hito 4
cierra el bucle del sistema de presencia del Hito 3 además de añadir el canal
de atención al cliente por WhatsApp.
