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

urlpatterns = [
    path('admin/', admin.site.urls),
    # Voice IVR bridge — puente IVR de voz.
    path('api/vox/', include('vox_bridge.urls')),
    # WhatsApp channel — canal WhatsApp (chatbot + presencia).
    path('api/whatsapp/', include('whatsapp.urls')),
    # Custom administration panel for CompanyUser accounts — panel de administración personalizado para cuentas CompanyUser.
    path('panel/', include('panel.urls')),
]
