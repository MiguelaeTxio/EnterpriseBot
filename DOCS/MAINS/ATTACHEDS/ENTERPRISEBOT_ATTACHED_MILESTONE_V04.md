# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V04.md

# ENTERPRISEBOT — ANEXO HITO V04 — CANAL WHATSAPP: CHATBOT CONVERSACIONAL Y SISTEMA DE PRESENCIA
**Estado:** EN PROGRESO
**Fecha de inicio:** 2026-04-09
**Prerequisito:** Hito 3 completado (Pasos 23–26 finalizados y validados E2E).

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

### 2.3. Gestión de número WhatsApp en Twilio

**Fase de desarrollo:** Sandbox de Twilio para WhatsApp. Número compartido
Twilio (~+14155238886). Los testers deben unirse al sandbox enviando el código
de unión al número de sandbox.

**Fase de producción:** El número Twilio existente +12603466780 se habilita
para WhatsApp a través del proceso de registro de sender en el Twilio Console
(Messaging → Senders → WhatsApp Senders → Self Sign-Up). No requiere número
nuevo si el número ya está aprobado por Meta.

**Nota crítica:** A partir del 17 de julio de 2024, Twilio eliminó los Legacy
WhatsApp Templates. Las plantillas se gestionan exclusivamente a través del
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

---

## SECCIÓN 3 — MODELO DE DATOS WHATSAPP

### 3.1. Nuevos modelos en whatsapp/models.py

#### WhatsAppSession — Sesión de conversación WhatsApp
    id                  AutoField (PK)
    company             ForeignKey(Company, on_delete=CASCADE)
    phone_number        CharField(max_length=20)   # número del usuario E.164
    session_start       DateTimeField(auto_now_add=True)
    last_message_at     DateTimeField(auto_now=True)
    is_active           BooleanField(default=True)

Una sesión agrupa todos los mensajes de un número de teléfono concreto con
una empresa concreta. Es activa mientras la ventana de 24h de Meta esté abierta.

La expiración de sesiones se gestiona mediante la tarea Celery
expire_whatsapp_sessions, que desactiva sesiones cuyo last_message_at sea
anterior a 24 horas.

#### WhatsAppMessage — Mensaje individual
    id                  AutoField (PK)
    session             ForeignKey(WhatsAppSession, on_delete=CASCADE)
    direction           CharField(choices=[('IN','Entrante'),('OUT','Saliente')])
    body                TextField()
    message_sid         CharField(max_length=50, blank=True)  # SID de Twilio
    content_sid         CharField(max_length=50, blank=True)  # HX... para templates
    timestamp           DateTimeField(auto_now_add=True)

Almacena el historial completo de la conversación. Se usa para reconstruir
el contexto de la sesión de chat de Gemini en cada llamada al webhook.

#### WhatsAppTemplate — Template aprobado por Meta
    id                  AutoField (PK)
    company             ForeignKey(Company, on_delete=CASCADE)
    name                CharField(max_length=200)
    content_sid         CharField(max_length=50)   # HX...
    category            CharField(choices=[
                            ('UTILITY','Utilidad'),
                            ('MARKETING','Marketing'),
                            ('AUTHENTICATION','Autenticación'),
                        ])
    language            CharField(max_length=10, default='es')
    is_active           BooleanField(default=True)
    created_at          DateTimeField(auto_now_add=True)

Registro centralizado de todos los templates aprobados disponibles para
la empresa. Permite gestionar el envío de templates desde código sin hardcodear
los SIDs.

### 3.2. Relación con modelos del Hito 3

Los modelos WhatsApp* se integran con la base de datos multiempresa existente:

- WhatsAppSession.company → ivr_config.Company
- El chatbot consulta ivr_config.Section, ivr_config.Contact y
  ivr_config.PresenceStatus para construir el contexto del agente.
- El webhook de presencia identifica al CompanyUser por
  ivr_config.Contact.phone_number (campo E.164).

---

## SECCIÓN 4 — ARQUITECTURA DE LA APP whatsapp

### 4.1. Estructura de archivos

    whatsapp/
    ├── __init__.py
    ├── apps.py
    ├── models.py
    ├── views.py          <- webhook entrante + webhook de presencia
    ├── urls.py           <- /api/whatsapp/incoming/ + /api/whatsapp/presence/
    ├── services.py       <- WhatsAppChatService + PresenceResponseService
    ├── admin.py          <- registro de modelos en Django admin
    ├── migrations/
    │   ├── __init__.py
    │   └── 0001_initial.py
    └── management/
        └── commands/
            ├── __init__.py
            └── seed_whatsapp_templates.py

### 4.2. URLs registradas

    /api/whatsapp/incoming/   <- POST — webhook mensajes entrantes de usuarios
    /api/whatsapp/presence/   <- POST — webhook respuestas de presencia (1h/2h/disponible)

Ambas rutas se registran en enterprise_core/urls.py bajo el prefijo
api/whatsapp/, junto a api/vox/ del IVR existente.

### 4.3. Flujo de mensaje entrante (/api/whatsapp/incoming/)

    1. Twilio POST /api/whatsapp/incoming/
       → IncomingWhatsAppView (csrf_exempt, POST)
       → Extraer: From (whatsapp:+34XXXXXXXXX), To (whatsapp:+12603466780), Body

    2. Resolver empresa:
       → PhoneNumber.objects.get(number=to_number, is_active=True)
       → company = phone_number.company

    3. Gestionar sesión:
       → Buscar WhatsAppSession activa para (company, from_number).
       → Si no existe o expiró → crear nueva WhatsAppSession.
       → Registrar WhatsAppMessage(direction='IN', body=body).

    4. Construir contexto del agente:
       → WhatsAppChatService.build_system_prompt(company, phone_number)
       → Incluye: nombre empresa, secciones activas, contactos internos
         con su PresenceStatus actual, forbidden_phrases del CorporateVoiceProfile.

    5. Reconstruir historial de chat:
       → WhatsAppMessage.objects.filter(session=session).order_by('timestamp')
       → Construir lista de turns para client.chats.create(history=[...])

    6. Enviar mensaje a Gemini:
       → chat = client.chats.create(
             model='gemini-2.5-flash',
             config=GenerateContentConfig(system_instruction=system_prompt),
             history=history_turns,
         )
       → response = chat.send_message(body)
       → reply_text = response.text

    7. Registrar respuesta:
       → WhatsAppMessage(direction='OUT', body=reply_text)

    8. Enviar respuesta por Twilio:
       → client.messages.create(
             from_='whatsapp:+12603466780',
             to=f'whatsapp:{from_number}',
             body=reply_text,
         )

    9. Retornar HTTP 200 vacío.

### 4.4. Flujo de webhook de presencia (/api/whatsapp/presence/)

Este webhook implementa la pieza diferida del Hito 3 documentada en
V03DOC_PRESENCE_SYSTEM.md, sección 4.

    1. Twilio POST /api/whatsapp/presence/
       → PresenceWhatsAppView (csrf_exempt, POST)
       → Extraer: From (whatsapp:+34XXXXXXXXX), Body ("1h" | "2h" | "disponible")

    2. Identificar CompanyUser:
       → Contact.objects.get(phone_number=from_number, is_internal=True)
       → company_user = contact.company_user

    3. Parsear respuesta:
       → "1h"          → ends_at = now() + timedelta(hours=1)
       → "2h"          → ends_at = now() + timedelta(hours=2)
       → "disponible"  → cerrar PresenceStatus activo, crear AVAILABLE

    4. Actualizar PresenceStatus:
       → PresenceResponseService.process_response(company_user, body)

    5. Enviar confirmación por WhatsApp:
       → Mensaje de texto libre dentro de la ventana de 24h.

    6. Retornar HTTP 200.

### 4.5. WhatsAppChatService en whatsapp/services.py

Servicio principal del chatbot. Responsabilidades:

- build_system_prompt(company, phone_number): construye el system prompt
  dinámico con el contexto de la empresa, secciones y presencia en tiempo real.
  Análogo a build_live_config() de ivr_config/services.py pero orientado
  a texto y WhatsApp.
- build_history(session): convierte los WhatsAppMessage de la sesión en
  la lista de turns compatible con client.chats.create(history=[...]).
- send_reply(from_number, to_number, reply_text): envía la respuesta usando
  el SDK de Twilio con prefijo whatsapp: en los números.

### 4.6. Tareas Celery en whatsapp/tasks.py

#### expire_whatsapp_sessions
Periodicidad: cada 30 minutos (Celery Beat).
Desactiva WhatsAppSession cuyo last_message_at sea anterior a 24 horas.

#### check_in_meeting_reminders
Implementación del pendiente del Hito 3 (V03DOC_PRESENCE_SYSTEM.md, seccion 3).
Periodicidad: cada 15 minutos (Celery Beat).
Lógica completa:
- Busca todos los PresenceStatus activos con status='IN_MEETING',
  ends_at=None y reminder_sent_at=None.
- Para cada uno, comprueba si han transcurrido 3 horas desde starts_at.
- Si es así, envía WhatsApp al Contact.phone_number del CompanyUser usando
  el template de recordatorio (WhatsAppTemplate con name='presence_reminder').
- Actualiza reminder_sent_at = now().

#### expire_presence_statuses
Implementación del pendiente del Hito 3 (V03DOC_PRESENCE_SYSTEM.md, seccion 3).
Periodicidad: cada 5 minutos (Celery Beat).
Lógica: igual a la especificada en V03DOC_PRESENCE_SYSTEM.md.

---

## SECCIÓN 5 — TEMPLATES WHATSAPP REQUERIDOS

### 5.1. Template de recordatorio de presencia

Nombre: presence_reminder
Categoría: UTILITY
Idioma: es
Cuerpo del template:
    ¿Sigues reunido? Responde con una de estas opciones:
    1h — Seguiré ocupado 1 hora más
    2h — Seguiré ocupado 2 horas más
    disponible — Ya estoy disponible

Este template debe crearse en el Content Template Builder del Console de Twilio
(Messaging → Content Template Builder → Create new) y someterse a aprobación
de Meta antes de su uso en producción. El ContentSid (HX...) resultante se
siembra en WhatsAppTemplate mediante el comando seed_whatsapp_templates.

### 5.2. Template de bienvenida fuera de sesión (opcional)

Nombre: welcome_message
Categoría: UTILITY
Idioma: es
Cuerpo del template:
    Hola {{1}}, soy el asistente virtual de {{2}}. ¿En qué puedo ayudarte hoy?

Para iniciar conversaciones proactivas business-initiated. Opcional en la
primera implementación — el chatbot opera en modo reactivo en la fase inicial.

---

## SECCIÓN 6 — MODIFICACIONES A ARCHIVOS EXISTENTES

### 6.1. enterprise_core/settings.py

Añadir 'whatsapp' a INSTALLED_APPS.

Añadir al CELERY_BEAT_SCHEDULE:
    'expire-whatsapp-sessions': {
        'task': 'whatsapp.tasks.expire_whatsapp_sessions',
        'schedule': crontab(minute='*/30'),
    },
    'check-in-meeting-reminders': {
        'task': 'whatsapp.tasks.check_in_meeting_reminders',
        'schedule': crontab(minute='*/15'),
    },
    'expire-presence-statuses': {
        'task': 'whatsapp.tasks.expire_presence_statuses',
        'schedule': crontab(minute='*/5'),
    },

### 6.2. enterprise_core/urls.py

Añadir:
    path('api/whatsapp/', include('whatsapp.urls')),

### 6.3. requirements.in

Sin cambios. twilio 9.10.4 y google-genai 1.69.0 cubren todos los requisitos.

---

## SECCIÓN 7 — COMANDOS DE GESTIÓN

### Comando: seed_whatsapp_templates

    python -m dotenv run python manage.py seed_whatsapp_templates

Siembra en BD los WhatsAppTemplate de Grupo Álvarez con los ContentSid
reales obtenidos del Content Template Builder de Twilio. Requiere que los
templates estén previamente creados y aprobados en el Console de Twilio.

### Secuencia de arranque del laboratorio

El canal WhatsApp opera sobre Django WSGI estándar (PythonAnywhere). No
requiere arrancar el bridge aiohttp para el chatbot de texto.

El webhook WhatsApp apunta a la URL estable de PythonAnywhere:
    https://enterprisebot-miguelaetxio.pythonanywhere.com/api/whatsapp/incoming/

No requiere ngrok — Django WSGI en PythonAnywhere es accesible públicamente.

---

## SECCIÓN 8 — HOJA DE RUTA

### Paso 1 — Creación de templates en Twilio Console

Acceder al Content Template Builder (Messaging → Content Template Builder).
Crear y someter a aprobación de Meta:
- Template presence_reminder (UTILITY, es).
- Template welcome_message (UTILITY, es) — opcional fase inicial.
Anotar los ContentSid (HX...) resultantes para usarlos en el seed.
Criterio de éxito: templates con estado Approved en el Console de Twilio.

### Paso 2 — Activación del Sandbox de Twilio para WhatsApp

Desde el Twilio Console (Messaging → Try it out → Send a WhatsApp message):
- Aceptar términos y activar el Sandbox.
- Conectar el teléfono de prueba enviando el código de unión al número sandbox.
- Configurar el webhook entrante del Sandbox:
  https://enterprisebot-miguelaetxio.pythonanywhere.com/api/whatsapp/incoming/
Criterio de éxito: enviar un mensaje al sandbox y recibir respuesta del chatbot.

### Paso 3 — PEA: whatsapp/__init__.py
Archivo vacío. Marca el directorio como paquete Python.

### Paso 4 — PEA: whatsapp/apps.py
Configuración de la app Django whatsapp.

### Paso 5 — PEA: whatsapp/models.py
Implementación completa de WhatsAppSession, WhatsAppMessage y WhatsAppTemplate
según la especificación de la Sección 3.

### Paso 6 — Migraciones
    python -m dotenv run python manage.py makemigrations whatsapp
    python -m dotenv run python manage.py migrate whatsapp
Verificar que las tres tablas se crean correctamente en MySQL.

### Paso 7 — PEA: whatsapp/admin.py
Registro de WhatsAppSession, WhatsAppMessage y WhatsAppTemplate en el admin
de Django para inspección durante el desarrollo.

### Paso 8 — PEA: whatsapp/services.py
Implementación completa de WhatsAppChatService (build_system_prompt,
build_history, send_reply) y PresenceResponseService (process_response).

### Paso 9 — PEA: whatsapp/tasks.py
Implementación completa de las tres tareas Celery:
- expire_whatsapp_sessions
- check_in_meeting_reminders
- expire_presence_statuses

### Paso 10 — PEA: whatsapp/views.py
Implementación de IncomingWhatsAppView y PresenceWhatsAppView según
el flujo detallado en la Sección 4.

### Paso 11 — PEA: whatsapp/urls.py
Definición de las dos rutas: /api/whatsapp/incoming/ y /api/whatsapp/presence/

### Paso 12 — PMA: enterprise_core/settings.py
Añadir whatsapp a INSTALLED_APPS y las tres tareas al CELERY_BEAT_SCHEDULE.

### Paso 13 — PMA: enterprise_core/urls.py
Añadir path('api/whatsapp/', include('whatsapp.urls')).

### Paso 14 — PEA: whatsapp/management/commands/seed_whatsapp_templates.py
Comando de gestión que siembra los WhatsAppTemplate de Grupo Álvarez con
los ContentSid reales. Idempotente: usa get_or_create.

### Paso 15 — Ejecución del seed de templates
    python -m dotenv run python manage.py seed_whatsapp_templates
Verificar en /admin/whatsapp/whatsapptemplate/ que los templates aparecen
con sus ContentSid correctos.

### Paso 16 — Validación E2E del chatbot de texto

Con el Sandbox configurado y los templates sembrados, validar:
1. Enviar mensaje al número sandbox desde el teléfono de prueba.
2. Verificar en logs Django que IncomingWhatsAppView recibe el webhook.
3. Verificar que WhatsAppChatService construye el prompt con contexto correcto.
4. Verificar que Gemini responde con coherencia corporativa.
5. Verificar que la respuesta llega al teléfono de prueba por WhatsApp.
6. Verificar que WhatsAppSession y WhatsAppMessage se crean en BD.

Criterio de éxito: conversación de al menos 3 turnos con contexto persistente
(el agente recuerda lo dicho en turnos anteriores de la misma sesión).

### Paso 17 — Validación E2E del webhook de presencia

Con un PresenceStatus de tipo IN_MEETING activo para un CompanyUser cuyo
Contact tenga phone_number válido:
1. Forzar check_in_meeting_reminders manualmente desde la shell de Django.
2. Verificar que llega el template de recordatorio al teléfono del CompanyUser.
3. Responder con "1h", "2h" o "disponible".
4. Verificar que PresenceWhatsAppView procesa la respuesta correctamente.
5. Verificar el PresenceStatus actualizado en BD y en /panel/presence/.

Criterio de éxito: ciclo completo recordatorio → respuesta → actualización de
presencia validado sin intervención manual en BD.

### Paso 18 — Habilitación del número de producción para WhatsApp

Cuando el desarrollo y validación en Sandbox sean satisfactorios:
1. Iniciar registro del sender +12603466780 para WhatsApp via Self Sign-Up.
2. Completar verificación Meta Business si no está completada.
3. Asociar el número al WhatsApp Business Account (WABA).
4. Actualizar webhook del número de producción a:
   https://enterprisebot-miguelaetxio.pythonanywhere.com/api/whatsapp/incoming/
5. Realizar prueba E2E con número de producción y teléfono real.

Criterio de éxito: el número +12603466780 opera simultáneamente como número
IVR de voz y número de chatbot WhatsApp.

### Paso 19 — Extensión del Panel: gestión de templates WhatsApp

Añadir al panel personalizado (/panel/) vistas para que el ADMIN de cada empresa
gestione sus WhatsAppTemplate:
- Listado de templates con estado de aprobación Meta.
- Detalle de template (solo lectura para ContentSid).

---

## SECCIÓN 9 — PENDIENTES DIFERIDOS

Nota: Cuando se aborden los puntos 2, 3 y 4 de esta sección (media, quick replies,
escalado a voz), evaluar obligatoriamente la creación del documento satélite
V04DOC_WHATSAPP_RICH_CONTENT.md bajo DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V04/

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
   registrarlos también como senders WhatsApp para operar en el mercado español.

---

## SECCIÓN 10 — PAH — REGISTRO DE SESIONES

### Sesión 2026-04-09
**Título:** Cambio Estratégico: Diseño del Hito 4 — Chatbot WhatsApp sobre Twilio
**Descripción:** Sesión de planificación estratégica. Se decide aprovechar la
espera de los números españoles para desarrollar el canal WhatsApp. Se realiza
investigación en línea comparativa entre Twilio for WhatsApp y Meta Cloud API
directa, concluyendo con Twilio como plataforma por reutilización total de
infraestructura, SDK ya instalado y sinergia con el IVR. Se analiza la
constelación documental del Hito 3, identificando dos puntos de integración
WhatsApp ya predefinidos en el sistema de presencia (webhook de respuesta a
recordatorios y tareas Celery). Se establece que el Hito 4 cierra el bucle del
sistema de presencia del Hito 3 además de añadir el canal de atención al cliente
por WhatsApp.
