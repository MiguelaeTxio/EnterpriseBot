# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0230_epidelivery_safety_dates_s163.py
# H31 (S163, sesión invasora): extintores y botiquines -- número de serie
# y fechas de caducidad, revisión y retimbrado en la entrega (todas
# opcionales; las filas que hay se quedan vacías).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0229_ack_whatsapp_status_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="epidelivery",
            name="serial_number",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Número de serie o matrícula"),
        ),
        migrations.AddField(
            model_name="epidelivery",
            name="expiry_date",
            field=models.DateField(blank=True, null=True, verbose_name="Caducidad"),
        ),
        migrations.AddField(
            model_name="epidelivery",
            name="review_date",
            field=models.DateField(blank=True, null=True, verbose_name="Próxima revisión"),
        ),
        migrations.AddField(
            model_name="epidelivery",
            name="retimbrado_date",
            field=models.DateField(blank=True, null=True, verbose_name="Retimbrado"),
        ),
    ]
