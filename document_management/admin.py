# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/admin.py
"""
NOTA: EmailTemplate NO se registra aqui. Miguel Angel pidio que sea
editable "desde la misma aplicacion"/"desde el panel" -- nunca dijo
admin, y al /admin/ de Django solo accede el como superusuario. La
edicion real de EmailTemplate vive en una vista de panel, pendiente de
confirmar su ubicacion exacta (ver conversacion S023).
"""
from django.contrib import admin

from .models import DocumentAlert


@admin.register(DocumentAlert)
class DocumentAlertAdmin(admin.ModelAdmin):
    list_display = (
        "id", "company", "subject_label", "document_label", "expiry_date",
        "status", "sent_at", "resolved_at",
    )
    list_filter = ("company", "status", "content_type")
    readonly_fields = ("created_at",)
