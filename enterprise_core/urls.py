# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/urls.py
"""
Main routing configuration for EnterpriseBot Core.
Registers all application URL namespaces under their canonical prefixes.
Cleaned: Removed legacy test_live application routes (April 2026).
---
Configuración principal de enrutamiento para EnterpriseBot Core.
Registra todos los espacios de nombres URL de aplicación bajo sus prefijos canónicos.
Saneado: Eliminadas las rutas de la aplicación legada test_live (Abril 2026).
"""

from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.views.decorators.cache import never_cache as _never_cache

urlpatterns = [

    # Web App Manifest — served from root so Chrome can detect the PWA.
    # Manifiesto de app web — servido desde la raíz para que Chrome detecte la PWA.
    path(
        "albaran-manifest.json",
        _never_cache(lambda request: HttpResponse(
            open("/home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/albaran_manifest.json").read(),
            content_type="application/manifest+json; charset=utf-8",
        )),
        name="albaran_manifest",
    ),

    # Service Worker — served from root scope so SW can control all panel routes.
    # Servido desde la raíz para que el SW controle todas las rutas del panel.
    path(
        "sw.js",
        _never_cache(lambda request: HttpResponse(
            open("/home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/sw_albaran.js").read(),
            content_type="application/javascript; charset=utf-8",
        )),
        name="sw_js",
    ),
    path('admin/', admin.site.urls),
    # Voice IVR bridge — puente IVR de voz.
    path('api/vox/', include('vox_bridge.urls')),
    # WhatsApp channel — canal WhatsApp (chatbot + presencia).
    path('api/whatsapp/', include('whatsapp.urls')),
    # Custom administration panel for CompanyUser accounts — panel de administración personalizado para cuentas CompanyUser.
    path('panel/', include('panel.urls')),
    # ASISTENCIA budget module — motor de presupuestos ASISTENCIA (Hito 16).
    path('panel/budgets/', include('budgets.urls', namespace='budgets')),
    # IRC-style section chat rooms — salas de chat IRC por sección (Hito 13).
    path('panel/chat/', include('chat.urls', namespace='chat')),
    # Unified Analytics Laboratory — Laboratorio de Análisis Unificado (Hito 20).
    path(
        'panel/analytics/',
        include('analytics.urls', namespace='analytics'),
    ),
]
