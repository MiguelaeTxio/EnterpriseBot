# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/settings.py
"""
Django settings for EnterpriseBot project.
Refactored April 2026 for Django 5.2.12 and Ngrok v3 Security Standards.
---
Configuración de Django para el proyecto EnterpriseBot.
Refactorizado en Abril de 2026 para los estándares de seguridad de Django 5.2.12 y Ngrok v3.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 1. CARGA DE VARIABLES DE ENTORNO / LOAD ENVIRONMENT VARIABLES
# Centralization of secrets and environment-specific configuration via .env file.
# Centralización de secretos y configuración específica del entorno a través del archivo .env.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# 2. CONFIGURACIÓN DE SEGURIDAD / SECURITY CONFIGURATION
# Core security identifiers and operational mode (Debug/Production).
# Identificadores de seguridad núcleo y modo de operación (Depuración/Producción).
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# API Key for Google Gemini 2.0 Flash Live (Standard for April 2026)
# Clave de API para Google Gemini 2.0 Flash Live (Estándar de Abril de 2026)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ✅ APRIL 2026 SECURITY POLICY: Dynamic Ngrok TLD Resolution
# Explicitly allowing .app, .dev, and .free.app for Ngrok v3 Agent compatibility.
# POLÍTICA DE SEGURIDAD ABRIL 2026: Resolución dinámica de TLDs de Ngrok.
# Se permite explícitamente .app, .dev, y .free.app para compatibilidad con el agente Ngrok v3.
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

# CSRF Trusted Origins for 2026 Secure Webhooks from Twilio and Ngrok tunnels.
# Orígenes de confianza CSRF para Webhooks seguros de 2026 de Twilio y túneles Ngrok.
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
    # Multicompany IVR configuration engine — motor de configuración IVR multiempresa.
    'ivr_config',
    # Custom administration panel for CompanyUser accounts — panel de administración personalizado para cuentas CompanyUser.
    'panel',
    # WhatsApp channel app — app del canal WhatsApp.
    'whatsapp',
    'work_order_processor',
    'fleet',
    # Supplier delivery notes and spare parts warehouse — albaranes de proveedor y almacén de repuestos (Hito 10).
    'spare_parts',
    # Bridge between digital work orders and the spare parts warehouse — puente entre partes digitales y almacén de repuestos (Hito 10, Paso 4).
    'workorder_spare_parts',
    # IRC-style section chat rooms and breakdown agent — salas de chat IRC y agente de averías.
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
    # Shared document infrastructure (alerts, PDF merge, email
    # templates, substitution) consumed by H23/H25 — infraestructura
    # documental compartida (Hito 26).
    'document_management',
]

# Middleware stack optimized for async processing in Django 5.2.12.
# Pila de middleware optimizada para procesamiento asíncrono en Django 5.2.12.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Blocks CompanyUser access to /admin/ — bloquea el acceso de CompanyUser a /admin/.
    'panel.middleware.CompanyUserAdminBlockMiddleware',
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
            # Activa el Strict Mode de MySQL para reforzar la integridad de datos.
            # Convierte en errores los avisos de truncado e incompatibilidad de tipo,
            # evitando la corrupción silenciosa de datos en operaciones de inserción/actualización.
            'sql_mode': 'STRICT_TRANS_TABLES',
        },
    }
}

# Advanced password validation for enterprise security compliance.
# Validación de contraseñas avanzada para cumplimiento de seguridad empresarial.
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
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
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 7. CELERY CONFIGURATION
# Broker, result backend and periodic task schedule for Celery Beat.
# Broker, backend de resultados y schedule de tareas periódicas para Celery Beat.
from celery.schedules import crontab

CELERY_BROKER_URL        = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND    = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_TIMEZONE          = TIME_ZONE
CELERY_ENABLE_UTC        = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_DEFAULT_QUEUE  = 'work_orders'

CELERY_BEAT_SCHEDULE = {
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

    # Sends presence reminders to CompanyUsers stuck in IN_MEETING for 3+ hours.
    # Envía recordatorios de presencia a CompanyUsers en IN_MEETING durante 3+ horas.
    'check-in-meeting-reminders': {
        'task':     'whatsapp.tasks.check_in_meeting_reminders',
        'schedule': crontab(minute='*/15'),
    },

    # Restores CompanyUsers to AVAILABLE when their PresenceStatus ends_at has passed.
    # Restaura CompanyUsers a AVAILABLE cuando su PresenceStatus ends_at ha expirado.
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
}
