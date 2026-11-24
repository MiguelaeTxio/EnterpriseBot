# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/urls.py
"""
Main routing configuration for EnterpriseBot Core.
Registers all application URL namespaces under their canonical prefixes.
Cleaned: Removed legacy test_live application routes (April 2026).
---
Configuracion principal de enrutamiento para EnterpriseBot Core.
Registra todos los espacios de nombres URL de aplicacion bajo sus prefijos
canonicos.
Saneado: Eliminadas las rutas de la aplicacion legada test_live (Abril 2026).
"""

from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.views.decorators.cache import never_cache as _never_cache
from hr_calendar import clockin as clockin_views
from budgets.api_driver import asset_links as _asset_links

from fleet import views_qr as fleet_qr_views
urlpatterns = [

    # Web App Manifest — served from root so Chrome can detect the PWA.
    # Manifiesto de app web — servido desde la raiz para que Chrome detecte la
    # PWA.
    path(
        "albaran-manifest.json",
        _never_cache(lambda request: HttpResponse(
            open(
                "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/"
                "panel/albaran_manifest.json"
            ).read(),
            content_type="application/manifest+json; charset=utf-8",
        )),
        name="albaran_manifest",
    ),

    # Service Worker — served from root scope so SW can control all panel
    # routes.
    # Servido desde la raiz para que el SW controle todas las rutas del panel.
    path(
        "sw.js",
        _never_cache(lambda request: HttpResponse(
            open(
                "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/"
                "panel/js/sw_albaran.js"
            ).read(),
            content_type="application/javascript; charset=utf-8",
        )),
        name="sw_js",
    ),
    # H24 (S129): la prueba de fichaje ha terminado -- /fichaje-prueba/
    # lleva a /fichaje/ y su service worker se da de baja solo en los
    # móviles que la instalaron (hr_calendar/clockin.py).
    path('fichaje-prueba/', clockin_views.retired_test_page),
    path('fichaje-prueba/sw.js', clockin_views.retired_test_sw),
    # H23 (S154): editor de fichas QR dentro del fichaje (contraseña
    # propia del editor, no la del usuario).
    path('fichaje/qr/', include('fleet.urls_qr_worker')),
    # H24 (S129): fichaje oficial -- recepción con la llave del
    # dispositivo de confianza (hr_calendar/clockin.py).
    path('fichaje/', include('hr_calendar.clockin_urls',
                             namespace='clockin')),
    # H11 (S162): albaranes de grúas -- página Grúas del panel
    # (/panel/gruas/) y el gruista dentro del fichaje
    # (/fichaje/albaranes/).
    path('', include('crane_albaranes.urls',
                     namespace='crane_albaranes')),
    # H37 (S138): salas de chat de la plataforma (formato IRC), con
    # enlace personal para quien no tiene cuenta del panel.
    path('sala/', include('chat.urls_room', namespace='chat_room')),
    # H37 (S138): App Links of the drivers' app (WhatsApp notice link).
    # App Links de la app de chóferes (enlace del aviso de WhatsApp).
    path('.well-known/assetlinks.json', _asset_links, name='asset_links'),
    path('admin/', admin.site.urls),
    # Voice IVR bridge — puente IVR de voz.
    path('api/vox/', include('vox_bridge.urls')),
    # WhatsApp channel — canal WhatsApp (chatbot + presencia).
    path('api/whatsapp/', include('whatsapp.urls')),
    # H37 (S133): API of the driver app (EBotDeliveryNotes).
    # API de la app del conductor.
    path(
        'api/driver/',
        include('budgets.urls_driver_api', namespace='driver_api'),
    ),
    # Custom administration panel for CompanyUser accounts — panel de
    # administracion personalizado para cuentas CompanyUser.
    # H23 (S154): página a la que lleva el QR de cada centro de gasto
    # (pública, solo lectura, por identificador no adivinable).
    path('ficha/<uuid:token>/', fleet_qr_views.qr_public_view,
         name='fleet_qr_public'),
    # S163 (invasora UX): nueva interfaz, app aparte (new_ui). Antes que
    # 'panel/' para que sus rutas no las tome el panel.
    path('panel/nueva-interfaz/', include('new_ui.urls')),
    # S156: pestaña «Correos CAE» del hub de Documentación (cae_mail).
    path('panel/cae/', include('cae_mail.urls', namespace='cae_mail')),
    path('panel/', include('panel.urls')),
    # ASISTENCIA budget module — motor de presupuestos ASISTENCIA (Hito 16).
    path('panel/budgets/', include('budgets.urls', namespace='budgets')),
    # IRC-style section chat rooms — salas de chat IRC por seccion (Hito 13).
    path('panel/chat/', include('chat.urls', namespace='chat')),
    # Unified Analytics Laboratory — Laboratorio de Analisis Unificado (Hito
    # 20).
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
        include(
            'workorder_spare_parts.urls',
            namespace='workorder_spare_parts',
        ),
    ),
    # Admin CRUD for supplier delivery notes — CRUD de administración de
    # albaranes de proveedor (Hito 10, gap 2026-07-08).
    path(
        'panel/albaranes/',
        include('delivery_notes.urls', namespace='delivery_notes'),
    ),
    # Cost-center documentation ingestion and classification —
    # ingesta y clasificación de documentación de centros de gasto
    # (Hito 23).
    path(
        'panel/documentacion-centros-gasto/',
        include('machine_documents.urls', namespace='machine_documents'),
    ),
    # HR vacation periods & calendar — periodos de vacaciones y calendario
    # de RRHH (Hito 24).
    path(
        'panel/vacaciones/',
        include('hr_calendar.urls', namespace='hr_calendar'),
    ),
    # Database-backed file explorer over Google Cloud Storage, with
    # folder-level permissions and two-tier deletion — explorador de
    # archivos sobre Google Cloud Storage servido desde base de datos,
    # con permisos por carpeta y borrado en dos niveles (Hito 29).
    path(
        'panel/explorador/',
        include('document_explorer.urls', namespace='document_explorer'),
    ),
    # Warehouse > supplier invoices uploaded by Ani's agent — Almacén >
    # facturas de proveedor que sube el agente de Ani (H28, S151).
    path(
        'panel/repuestos/facturas-proveedor/',
        include('supplier_invoices.urls', namespace='supplier_invoices'),
    ),
    # Warehouse > photo inventory — Almacén > inventario por fotos (H10,
    # S151). Solo superusuario de momento.
    path(
        'panel/repuestos/inventario/',
        include('warehouse_inventory.urls', namespace='warehouse_inventory'),
    ),
]
