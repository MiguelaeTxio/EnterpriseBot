# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/settings.py
"""
Django settings for EnterpriseBot project.
Refactored April 2026 for Django 5.2.12 and Ngrok v3 Security Standards.
---
Configuración de Django para el proyecto EnterpriseBot.
Refactorizado en Abril de 2026 para los estándares de seguridad de Django
5.2.12 y Ngrok v3.
"""

import os
from pathlib import Path

from celery.schedules import crontab
from dotenv import load_dotenv

# 1. CARGA DE VARIABLES DE ENTORNO / LOAD ENVIRONMENT VARIABLES
# Centralization of secrets and environment-specific configuration via .env
# file.
# Centralización de secretos y configuración específica del entorno a través
# del archivo .env.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# 2. CONFIGURACIÓN DE SEGURIDAD / SECURITY CONFIGURATION
# Core security identifiers and operational mode (Debug/Production).
# Identificadores de seguridad núcleo y modo de operación
# (Depuración/Producción).
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# API Key for Google Gemini 2.0 Flash Live (Standard for April 2026)
# Clave de API para Google Gemini 2.0 Flash Live (Estándar de Abril de 2026)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Token compartido para el webhook document_explorer.RegisterUploadedObjectView
# (H29, S040) -- lo usa el agente de migración H28 para avisar al servidor,
# justo tras cada subida con éxito, de qué objeto acaba de escribir en GCS.
# Debe fijarse en .env, y el agente debe llevar el mismo valor. Sin valor,
# la vista rechaza toda petición (ver `if not expected`).
H28_AGENT_API_TOKEN = os.getenv('H28_AGENT_API_TOKEN')

# ✅ APRIL 2026 SECURITY POLICY: Dynamic Ngrok TLD Resolution
# Explicitly allowing .app, .dev, and .free.app for Ngrok v3 Agent
# compatibility.
# POLÍTICA DE SEGURIDAD ABRIL 2026: Resolución dinámica de TLDs de Ngrok.
# Se permite explícitamente .app, .dev, y .free.app para compatibilidad con el
# agente Ngrok v3.
ALLOWED_HOSTS = [
    'MiguelAeTxio.pythonanywhere.com',
    'enterprisebot-miguelaetxio.pythonanywhere.com',
    '.ngrok-free.app',
    '.ngrok-free.dev',
    '.ngrok.app',
    '.ngrok.dev',
    '127.0.0.1',
    'localhost'
]

# H37 (S132): public URL of the platform, for links sent outside the panel
# (WhatsApp messages and template buttons).
# URL pública de la plataforma, para los enlaces que salen del panel
# (mensajes de WhatsApp y botones de plantilla).
PLATFORM_BASE_URL = "https://enterprisebot-miguelaetxio.pythonanywhere.com"

# CSRF Trusted Origins for 2026 Secure Webhooks from Twilio and Ngrok tunnels.
# Orígenes de confianza CSRF para Webhooks seguros de 2026 de Twilio y túneles
# Ngrok.
CSRF_TRUSTED_ORIGINS = [
    'https://*.ngrok-free.app',
    'https://*.ngrok-free.dev',
    'https://*.ngrok.app',
    'https://*.ngrok.dev'
]

# 3. DEFINICIÓN DE APLICACIONES / APPLICATIONS DEFINITION
# Project application ecosystem and standard Django modules.
# Ecosistema de aplicaciones del proyecto y módulos estándar de Django.
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Shared AI services (Gemini client helper) — servicios de IA
    # compartidos (helper de cliente Gemini). Hito 10, principio DRY.
    'ai_services',
    # Core voice bridge — puente de voz principal.
    'vox_bridge',
    # Multicompany IVR configuration engine — motor de configuración IVR
    # multiempresa.
    'ivr_config',
    # Custom administration panel for CompanyUser accounts — panel de
    # administración personalizado para cuentas CompanyUser.
    'panel',
    # WhatsApp channel app — app del canal WhatsApp.
    'whatsapp',
    'work_order_processor',
    'fleet',
    # Supplier delivery notes and spare parts warehouse — albaranes de
    # proveedor y almacén de repuestos (Hito 10).
    'spare_parts',
    # Bridge between digital work orders and the spare parts warehouse — puente
    # entre partes digitales y almacén de repuestos (Hito 10, Paso 4).
    'workorder_spare_parts',
    # IRC-style section chat rooms and breakdown agent — salas de chat IRC y
    # agente de averías.
    'chat',
    # ASISTENCIA budget engine — motor de presupuestos ASISTENCIA.
    'budgets',
    # Unified Analytics Laboratory — Laboratorio de Análisis Unificado.
    'analytics',
    # Machine History Viewer — Visor de Historial de Maquinas (Hito 22).
    'history',
    # Admin CRUD for supplier delivery notes — CRUD de administración
    # de albaranes de proveedor (Hito 10, gap 2026-07-08).
    'delivery_notes',
    # Cost-center documentation ingestion and classification — ingesta
    # y clasificación de documentación de centros de gasto (Hito 23).
    'machine_documents',
    # Vacation/absence calendar management — gestión del calendario de
    # vacaciones/ausencias (Hito 24).
    'hr_calendar',
    # Insurance renewal reports -- informes de renovación de seguros
    # (pestaña Seguros de Documentación, S152).
    'insurance',
    # Personnel documentation ingestion and classification — ingesta y
    # clasificación de documentación de personal (Hito 25).
    'personal_documents',
    # Domain routing (machine vs. personnel) for automatic folder
    # ingestion — enrutado de dominio (máquina vs. personal) para la
    # ingesta automática de carpeta (Hito 23/25, S024).
    'document_ingestion',
    # Shared document infrastructure (alerts, PDF merge, email
    # templates, substitution) consumed by H23/H25 — infraestructura
    # documental compartida (Hito 26).
    'document_management',
    # DB-backed index over every governed GCS bucket, folder-level
    # permissions and two-tier deletion, feeding the panel file
    # explorer — explorador de archivos y gobierno documental sobre
    # Google Cloud Storage (Hito 29).
    'document_explorer',
    # Real worksite ("obra") model -- seam for future Cliente/Proveedor/
    # facturación models (H31, S115, deuda técnica 4.23) -- modelo real de
    # obra, pensado como costura para los futuros modelos de Cliente/
    # Proveedor/facturación.
    'worksites',
    # Supplier invoices uploaded by Ani's agent: warehouse pipeline
    # (delivery notes, warehouse, work orders) -- facturas de proveedor
    # de FACTURACION PROVEEDORES, pipeline del almacén (H28, S151).
    'supplier_invoices',
    'warehouse_inventory',
]

# Middleware stack optimized for async processing in Django 5.2.12.
# Pila de middleware optimizada para procesamiento asíncrono en Django 5.2.12.
MIDDLEWARE = [
    # S153: apunta las peticiones lentas (>3 s) con sus consultas en
    # logs/slow_requests.log, para ver qué hace lenta una página.
    'panel.slow_requests.SlowRequestLogMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Blocks CompanyUser access to /admin/ — bloquea el acceso de CompanyUser a
    # /admin/.
    'panel.middleware.CompanyUserAdminBlockMiddleware',
    # S117: htmx + sesión caducada -> HX-Redirect al login completo en
    # vez de incrustar la página de login en el hueco del fragmento.
    'panel.middleware.HtmxLoginRedirectMiddleware',
    # H37 (S132): historial de páginas por usuario en BD para el botón
    # "Volver" (panel/navigation_history.py).
    'panel.navigation_history.NavigationHistoryMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'enterprise_core.urls'

# Template engine configuration for secure frontend rendering.
# Configuración del motor de plantillas para renderizado frontend seguro.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # CompanyUser y Company disponibles en TODAS las
                # plantillas -- la sidebar los exige y hasta S037 cada
                # vista tenia que inyectarlos a mano, perdiendo medio
                # menu la que se olvidara. Ver panel/context_processors.
                'panel.context_processors.company_context',
                # H31 (S94): estado real (BD) de los acordeones del
                # sidebar, sustituye sessionStorage. Ver
                # panel/context_processors.sidebar_navigation_context.
                'panel.context_processors.sidebar_navigation_context',
                # H37 (S132): URL de "Volver" (panel_back_url).
                'panel.navigation_history.back_url_context',
                # H31 (S94): a dónde lleva el enlace "Documentación"
                # del sidebar -- al hub o directo a la última ficha de
                # persona abierta. Ver
                # panel/context_processors.documentation_sidebar_link_context.
                'panel.context_processors.documentation_sidebar_link_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'enterprise_core.wsgi.application'

# 4. CONFIGURACIÓN DE BASE DE DATOS / DATABASE CONFIGURATION
# MySQL production connection for persistent interaction logging.
# Conexión de producción MySQL para el registro persistente de interacciones.
SILENCED_SYSTEM_CHECKS = ["models.W036"]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': 'MiguelAeTxio',
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': 'MiguelAeTxio.mysql.pythonanywhere-services.com',
        'PORT': '3306',
        'OPTIONS': {
            # Activates MySQL Strict Mode to enforce data integrity.
            # Escalates truncation and type mismatch warnings into errors,
            # preventing silent data corruption on insert/update operations.
            # Activa el Strict Mode de MySQL para reforzar la integridad de
            # datos.
            # Convierte en errores los avisos de truncado e incompatibilidad de
            # tipo,
            # evitando la corrupción silenciosa de datos en operaciones de
            # inserción/actualización.
            'sql_mode': 'STRICT_TRANS_TABLES',
        },
    }
}

# Advanced password validation for enterprise security compliance.
# Validación de contraseñas avanzada para cumplimiento de seguridad
# empresarial.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'UserAttributeSimilarityValidator'
        ),
    },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'CommonPasswordValidator'
        ),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'NumericPasswordValidator'
        ),
    },
]

# 5. INTERNACIONALIZACIÓN / INTERNATIONALIZATION
# Regional localization and timezone settings (Europe/Madrid).
# Configuración de localización regional y zona horaria (Europe/Madrid).
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'Europe/Madrid'
USE_I18N = True
USE_TZ = True

# Locale settings — decimal separator for ES locale.
# Configuracion de locale — separador decimal para locale ES.
# DecimalField inputs accept comma as decimal separator (e.g. '5,00').
# Los campos DecimalField aceptan coma como separador decimal (ej: '5,00').
USE_L10N = True
DECIMAL_SEPARATOR = ','
USE_THOUSAND_SEPARATOR = False

# 6. ARCHIVOS ESTÁTICOS / STATIC FILES
# Path definition for static asset management.
# Definición de rutas para la gestión de activos estáticos.
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
# INCIDENTE REAL S102: `STATICFILES_STORAGE` (ajuste heredado,
# pre-Django 4.2) declaraba `ManifestStaticFilesStorage`, pero Django
# 5.2 en runtime solo mira `STORAGES` (verificado con datos reales:
# `settings.STORAGES['staticfiles']['BACKEND']` devolvía el
# `StaticFilesStorage` por defecto, SIN hash, pese a este ajuste) --
# como `STORAGES` nunca se había declarado explícitamente aquí, el
# versionado por hash de los estáticos NUNCA ha estado activo de
# verdad en todo el proyecto. Efecto real: cualquier cambio de CSS/JS
# se sirve siempre con la misma URL exacta (`/static/panel/css/
# panel.css`), así que el navegador no tiene ninguna señal para dejar
# de servir su copia en caché -- un cambio real podía quedar invisible
# hasta que el usuario limpiara caché a mano. `STATICFILES_STORAGE` se
# retira (ignorado silenciosamente por Django, dejarlo era una gotera
# de configuración muerta) -- `STORAGES['default']` reproduce el
# `FileSystemStorage` implícito que ya se usaba (no había
# `DEFAULT_FILE_STORAGE` declarado tampoco). `staticfiles` usa
# `LenientManifestStaticFilesStorage` (ver enterprise_core/storage.py)
# en vez de la `ManifestStaticFilesStorage` vanilla -- activarla tal
# cual tumbaba `collectstatic` por completo (bootstrap.bundle.min.js
# referencia un .map que nunca se vendorizó), verificado con una
# recreación real del comando antes de desplegar.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "enterprise_core.storage.LenientManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 7. CELERY CONFIGURATION
# Broker, result backend and periodic task schedule for Celery Beat.
# Broker, backend de resultados y schedule de tareas periódicas para Celery
# Beat.
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv(
    'CELERY_RESULT_BACKEND', 'redis://localhost:6379/0',
)
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_DEFAULT_QUEUE = 'work_orders'
# S140 (H37): no task result is ever read (no AsyncResult, .get(), chord
# or group in the project). With results on, every process that sends a
# task (web, bridge, worker) keeps its own pub/sub connection to Redis to
# wait for results nobody reads; on 28/10/2026 Redis reached its client
# limit ("max number of clients reached") and uploading a service sheet
# to the room failed with a 500.
# No se lee nunca el resultado de una tarea (ni AsyncResult, ni .get(),
# ni chord ni group). Con resultados, cada proceso que manda una tarea
# (web, bridge, worker) deja abierta su propia conexión pub/sub a Redis
# para esperar resultados que nadie lee; el 28/10/2026 Redis llegó a su
# límite de clientes y subir una hoja de servicio a la sala dio un 500.
CELERY_TASK_IGNORE_RESULT = True

# ---------------------------------------------------------------------------
# Resiliencia ante caída del worker (S025) -- hallazgo real de Miguel
# Ángel: un lote de 95 documentos se quedó a medias (4 documentos
# perdidos, #207-210) sin ningún error en el log. Causa raíz
# confirmada: Celery, con la configuración por defecto que tenía este
# proyecto hasta ahora (acks_late=False, prefetch_multiplier=4),
# reserva hasta 4 tareas en el buffer local del worker ANTES de
# ejecutarlas, y las marca como "entregadas" ante Redis en ese mismo
# momento -- no cuando terminan. Si el proceso muere con esas tareas
# en el buffer (el worker corre en un contenedor separado de
# PythonAnywhere, reiniciado varias veces hoy durante los despliegues
# de esta sesión), se pierden sin dejar ningún rastro. Encajaba
# exactamente con los 4 documentos perdidos (concurrency=1 x
# prefetch_multiplier=4 por defecto = 4).
#
# Verificado en línea (directriz 4.4, 2026-07-20) contra la
# documentación oficial de Celery 5.6.3 (misma versión instalada) --
# combinación recomendada exactamente para este caso:
#   - CELERY_TASK_ACKS_LATE: la tarea solo se confirma como entregada
#     tras terminar (éxito o fallo), nunca al recibirla -- si el
#     worker muere antes de acabarla, Redis la redistribuye a otro
#     worker (o al mismo, tras recuperarse) en vez de perderla.
#   - CELERY_WORKER_PREFETCH_MULTIPLIER = 1: reduce el buffer de
#     tareas reservadas por adelantado al mínimo (1, igual a la
#     concurrencia real de este worker) -- si hoy se perdían hasta 4
#     tareas de golpe, a partir de ahora el máximo posible es 1.
#   - CELERY_TASK_REJECT_ON_WORKER_LOST: cubre el caso distinto de que
#     el worker muera A MITAD de ejecutar una tarea (acks_late por sí
#     solo NO lo cubre -- Celery confirma la entrega igualmente si el
#     proceso hijo termina abruptamente mientras corre, ver
#     documentación oficial) -- con este ajuste, esa tarea también se
#     reencola en vez de darse por perdida.
#
# Seguro para las tareas reales de este proyecto porque todas ya son
# idempotentes a nivel de documento individual (ver docstring de
# process_machine_document_batch/process_personal_document_batch:
# "solo se recogen las filas PENDING en cada ejecución" -- un
# reintento tras una caída nunca reprocesa lo que ya tuvo éxito).
# ---------------------------------------------------------------------------
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True

CELERY_BEAT_SCHEDULE = {
    # S154 (H23): libro historial de las grúas A/H -- lee los escaneos
    # nuevos (las revisiones que faltaban, subidas por cualquier vía) y
    # cierra las reconstrucciones ya firmadas en el PC de Yolanda.
    'logbook-pipeline': {
        'task':     'fleet.tasks.logbook_pipeline_task',
        'schedule': crontab(minute='*/10'),
    },
    # S149: lecturas de albaranes cortadas a medias (un reinicio de
    # Celery en un despliegue) se reanudan solas donde se quedaron.
    'resume-albaran-batches': {
        'task':     'hr_calendar.tasks.resume_albaran_batches_task',
        'schedule': crontab(minute='*/5'),
    },
    # ---------------------------------------------------------------------------
    # WHATSAPP CHANNEL TASKS
    # Tareas del canal WhatsApp — Hito 4.
    # ---------------------------------------------------------------------------

    # Deactivates WhatsApp sessions whose Meta 24-hour window has expired.
    # Desactiva sesiones WhatsApp cuya ventana Meta de 24 horas ha expirado.
    'expire-whatsapp-sessions': {
        'task':     'whatsapp.tasks.expire_whatsapp_sessions',
        'schedule': crontab(minute='*/30'),
    },

    # Sends presence reminders to CompanyUsers stuck in IN_MEETING for 3+
    # hours.
    # Envía recordatorios de presencia a CompanyUsers en IN_MEETING durante 3+
    # horas.
    'check-in-meeting-reminders': {
        'task':     'whatsapp.tasks.check_in_meeting_reminders',
        'schedule': crontab(minute='*/15'),
    },

    # Restores CompanyUsers to AVAILABLE when their PresenceStatus ends_at has
    # passed.
    # Restaura CompanyUsers a AVAILABLE cuando su PresenceStatus ends_at ha
    # expirado.
    'expire-presence-statuses': {
        'task':     'whatsapp.tasks.expire_presence_statuses',
        'schedule': crontab(minute='*/5'),
    },

    # ---------------------------------------------------------------------------
    # CHAT IRC TASKS — Hito 13
    # Tareas del módulo de chat IRC — Hito 13.
    # ---------------------------------------------------------------------------
    # 'purge-old-chat-messages' ELIMINADA (2026-07-16, S023): ChatRoom/
    # ChatMessage y purge_old_chat_messages() se retiraron en H17 Paso 1
    # (solo queda BreakdownTicket, comunicación uno a uno vía WhatsApp).
    # Esta entrada llevaba desde entonces apuntando a una tarea inexistente
    # -- disparándose en el vacío cada día a las 3:00, sin fallar visible
    # porque Celery simplemente no encontraba la tarea registrada. Bug real
    # detectado y corregido en la misma sesión, fuera de alcance de H26/H23
    # (ver ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md para el registro).
    # El hueco horario (3:00) se reutiliza para la tarea de alertas de
    # documentos de H26 en cuanto esa tarea exista (decisión explícita de
    # Miguel Ángel, S023).

    # ---------------------------------------------------------------------------
    # SHARED DOCUMENT INFRASTRUCTURE TASKS — Hito 26
    # Tareas de infraestructura documental compartida — Hito 26.
    # ---------------------------------------------------------------------------

    # Detects documents whose expiry alert date has been reached and sends
    # a WhatsApp alert to their assigned contact(s) via document_expiry_alert.
    # Detecta documentos cuya fecha de aviso ha llegado y envía una alerta
    # WhatsApp a su(s) contacto(s) asignado(s) vía document_expiry_alert.
    'send-document-expiry-alerts': {
        'task':     'document_management.tasks.send_document_expiry_alerts',
        # Cambiado de 3:00 a 8:00 (H30 S50): un aviso de WhatsApp a las
        # 3 de la madrugada a un contacto real es un disparate, aunque
        # el resto de tareas nocturnas de ese hueco horario tengan
        # sentido a esa hora. Miguel Angel: "nos puede partir la
        # espalda con un palo".
        'schedule': crontab(hour=8, minute=0),
    },

    # ---------------------------------------------------------------------------
    # PERSONAL DOCUMENT INGESTION — Hito 25
    # Ingesta de documentación de personal — Hito 25.
    # ---------------------------------------------------------------------------

    # Self-healing: re-attempts automatic worker pre-registration for
    # PersonalDocument rows left unassigned when route_ingested_files
    # was interrupted mid-task (deploy-triggered worker restart, a
    # transient Gemini failure, etc.) -- real incident 2026-07-23
    # (S030), Miguel Ángel: "el código tiene que ser resiliente...
    # debe de autocurarse".
    # Autocuración: reintenta el pre-registro automático de
    # trabajadores para PersonalDocument que quedaron sin asignar
    # porque route_ingested_files se interrumpió a mitad de tarea
    # (reinicio del worker disparado por un despliegue, un fallo
    # puntual de Gemini, etc.) -- incidente real 2026-07-23 (S030).
    'self-heal-unassigned-personal-documents': {
        'task': (
            'document_ingestion.tasks.'
            'self_heal_unassigned_personal_documents'
        ),
        'schedule': crontab(minute='*/15'),
    },

    # ---------------------------------------------------------------------------
    # FILE EXPLORER — Hito 29
    # Explorador de archivos — Hito 29.
    # ---------------------------------------------------------------------------

    # Red de seguridad de baja frecuencia (H29, S040) -- el mecanismo
    # PRINCIPAL de consistencia del índice es RegisterUploadedObjectView,
    # el webhook al que el agente H28 avisa al momento de cada subida
    # (ver document_explorer/views.py). Esta tarea existe solo para el
    # caso de que ese aviso falle (agente caído a mitad, sin red en ese
    # instante, etc.) -- Miguel Ángel fue explícito en que el panel NO
    # debe depender de un refresco periódico para ver lo que ya está en
    # GCS, así que la cadencia es deliberadamente baja (una vez a la
    # hora), nunca el camino que se espera que se use en el día a día.
    'refresh-quarantine-index-safety-net': {
        'task':     'document_explorer.tasks.refresh_quarantine_index_task',
        'schedule': crontab(minute=0),
    },

    # Always-on Task real de consumo de cuarentena (H29, S040, punto 2
    # de la hoja de ruta) -- clasifica hasta 40 archivos por pasada,
    # cada 10 minutos. MACHINE se reubica de verdad cuando se resuelve
    # con certeza; PERSONAL y MACHINE sin resolver quedan clasificados
    # pero marcados para revisión humana, nunca movidos a ciegas.
    'consume-quarantine': {
        'task':     'document_explorer.tasks.consume_quarantine_task',
        'schedule': crontab(minute='*/5'),
    },

    # H30 (S123), punto 7: alerta por WhatsApp si el agente H28 lleva
    # más de 15 minutos sin latido (una vez por caída, y al volver).
    'check-system-agents': {
        'task':     'document_explorer.tasks.check_system_agents_task',
        'schedule': crontab(minute='*/5'),
    },

    # H31 (S134): foto de carné recortada del DNI o del permiso de
    # conducir para las personas con un documento nuevo de ese tipo.
    'extract-id-photos': {
        'task':     'document_explorer.tasks.extract_id_photos_task',
        'schedule': crontab(minute='*/15'),
    },

    # H30 (S135): suministros del surtidor (GasoGes) -> lecturas de km
    # y horas de los centros de gasto (últimos 3 días). S137, Miguel
    # Ángel: cada 5 minutos, para que la pregunta por WhatsApp llegue a
    # los pocos minutos de repostar y no una hora después.
    'sync-gasoges': {
        'task':     'fleet.tasks.sync_gasoges_task',
        'schedule': crontab(minute='*/5'),
    },

    # H24 (S141): recordatorio por WhatsApp a quien no ha fichado la
    # entrada o la salida. S143: cada trabajador marca sus avisos (3
    # minutos después, media hora, cada hora...), así que la tarea corre
    # cada minuto para que salgan a su hora.
    'send-clock-reminders': {
        'task':     'hr_calendar.tasks.send_clock_reminders_task',
        'schedule': crontab(minute='*'),
    },

    # H24 (S146): copia de seguridad diaria de la base de datos a las
    # 3:00, volcada al cubo y bajada a OneDrive por el agente H28.
    'backup-database': {
        'task':     'document_explorer.tasks.backup_database_task',
        'schedule': crontab(hour=3, minute=0),
    },

    # H28 (S151): facturas que el agente de facturas del PC de Ani sube
    # al cubo (FACTURACION PROVEEDORES/FACTURAS NUEVAS) -> se indexan y
    # se procesan.
    'sweep-invoice-folder': {
        'task':     'supplier_invoices.tasks.sweep_invoice_folder_task',
        'schedule': crontab(minute='*/5'),
    },
}

# H30 (S123): destinatarios (PersonIdentity.pk) de la alerta de caída
# de agentes de sistema -- Miguel Ángel (ficha 250).
SYSTEM_AGENT_ALERT_PERSON_IDS = [
    int(value) for value in os.getenv(
        'SYSTEM_AGENT_ALERT_PERSON_IDS', '250',
    ).split(',') if value.strip()
]
