# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/urls.py
from django.contrib import admin
from django.urls import path, include

"""
Main routing configuration for EnterpriseBot Core.
Cleaned: Removed legacy test_live application routes (April 2026).
---
Configuración principal de enrutamiento para EnterpriseBot Core.
Saneado: Eliminadas las rutas de la aplicación legada test_live (Abril 2026).
"""

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/vox/', include('vox_bridge.urls')),
    # Custom administration panel for CompanyUser accounts — panel de administración personalizado para cuentas CompanyUser.
    path('panel/', include('panel.urls')),
]
