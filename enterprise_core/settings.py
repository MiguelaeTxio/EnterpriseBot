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
    'vox_bridge',
]

# Middleware stack optimized for async processing in Django 5.2.12.
# Pila de middleware optimizada para procesamiento asíncrono en Django 5.2.12.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
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
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': 'MiguelAeTxio',
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': 'MiguelAeTxio.mysql.pythonanywhere-services.com',
        'PORT': '3306',
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

# 6. ARCHIVOS ESTÁTICOS / STATIC FILES
# Path definition for static asset management.
# Definición de rutas para la gestión de activos estáticos.
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
