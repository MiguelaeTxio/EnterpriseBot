# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/urls.py
"""
Main routing configuration for EnterpriseBot Core.
Registers all application URL namespaces under their canonical prefixes.
Cleaned: Removed legacy test_live application routes (April 2026).
---
Configuracion principal de enrutamiento para EnterpriseBot Core.
Registra todos los espacios de nombres URL de aplicacion bajo sus prefijos canonicos.
Saneado: Eliminadas las rutas de la aplicacion legada test_live (Abril 2026).
"""

from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.views.decorators.cache import never_cache as _never_cache

urlpatterns = [

    # Web App Manifest — served from root so Chrome can detect the PWA.
    # Manifiesto de app web — servido desde la raiz para que Chrome detecte la PWA.
    path(
        "albaran-manifest.json",
        _never_cache(lambda request: HttpResponse(
            open("/home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/albaran_manifest.json").read(),
            content_type="application/manifest+json; charset=utf-8",
        )),
        name="albaran_manifest",
    ),

    # Service Worker — served from root scope so SW can control all panel routes.
    # Servido desde la raiz para que el SW controle todas las rutas del panel.
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
    # Custom administration panel for CompanyUser accounts — panel de administracion personalizado para cuentas CompanyUser.
    path('panel/', include('panel.urls')),
    # ASISTENCIA budget module — motor de presupuestos ASISTENCIA (Hito 16).
    path('panel/budgets/', include('budgets.urls', namespace='budgets')),
    # IRC-style section chat rooms — salas de chat IRC por seccion (Hito 13).
    path('panel/chat/', include('chat.urls', namespace='chat')),
    # Unified Analytics Laboratory — Laboratorio de Analisis Unificado (Hito 20).
    path(
        'panel/analytics/',
        include('analytics.urls', namespace='analytics'),
    ),
    # Machine History Viewer — Visor de Historial de Maquinas (Hito 22).
    path(
        'panel/history/',
        include('history.urls', namespace='history'),
    ),
    # Supplier delivery notes & spare parts warehouse — Albaranes de
    # proveedores y almacén de repuestos (Hito 10).
    path(
        'panel/spare-parts/',
        include('spare_parts.urls', namespace='spare_parts'),
    ),
    # Bridge between digital work orders and the spare parts warehouse —
    # puente entre partes digitales y almacén de repuestos (Hito 10, Paso 4).
    path(
        'panel/repuestos/',
        include('workorder_spare_parts.urls', namespace='workorder_spare_parts'),
    ),
    # Admin CRUD for supplier delivery notes — CRUD de administración de
    # albaranes de proveedor (Hito 10, gap 2026-07-08).
    path(
        'panel/albaranes/',
        include('delivery_notes.urls', namespace='delivery_notes'),
    ),
    # Hidden token-gated APK/manifest endpoint — not linked from any
    # menu or template, see mimoo_updates app.
    # Endpoint oculto de APK/manifiesto protegido por token — no
    # enlazado desde ningun menu ni plantilla, ver app mimoo_updates.
    path('mimoo-updates/', include('mimoo_updates.urls', namespace='mimoo_updates')),
]
