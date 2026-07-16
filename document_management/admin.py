# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/admin.py
from django.contrib import admin

from .models import DocumentAlert, EmailTemplate


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "subject", "is_active", "updated_at")
    list_filter = ("company", "is_active")
    search_fields = ("name", "subject", "body")


@admin.register(DocumentAlert)
class DocumentAlertAdmin(admin.ModelAdmin):
    list_display = (
        "id", "company", "content_type", "object_id", "expiry_date",
        "status", "sent_at", "resolved_at",
    )
    list_filter = ("company", "status", "content_type")
    readonly_fields = ("created_at",)
