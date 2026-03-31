# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # La propiedad .urls proporciona la terna (patterns, app_name, namespace) correcta
    path('admin/', admin.site.urls), 
    path('api/vox/', include('vox_bridge.urls')),
    path('test/', include('test_live.urls')),
]
