# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0229_ack_whatsapp_status_s149.py
# H24 (S149, sesión invasora): estado de entrega del WhatsApp de cada
# envío de circular (para el informe del alta en el fichaje).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0228_circular_alta_fichaje_panel_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentacknowledgment",
            name="whatsapp_sid",
            field=models.CharField(
                blank=True, default="", max_length=64,
                verbose_name="Mensaje de WhatsApp (SID)"),
        ),
        migrations.AddField(
            model_name="documentacknowledgment",
            name="whatsapp_status",
            field=models.CharField(
                blank=True, default="", max_length=20,
                verbose_name="Estado del WhatsApp"),
        ),
        migrations.AddField(
            model_name="documentacknowledgment",
            name="whatsapp_status_at",
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name="Estado del WhatsApp (fecha/hora)"),
        ),
    ]
