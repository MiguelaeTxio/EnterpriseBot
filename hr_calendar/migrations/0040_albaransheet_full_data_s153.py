# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0040_albaransheet_full_data_s153.py
# S153 (sesión invasora): copia digital completa del albarán de trabajo
# (todos sus datos y su transcripción) y su archivo en el cubo.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0039_clockevent_claimed_at_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="albaransheet",
            name="full_data",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="Datos completos"),
        ),
        migrations.AddField(
            model_name="albaransheet",
            name="full_text",
            field=models.TextField(
                blank=True, verbose_name="Transcripción completa"),
        ),
        migrations.AddField(
            model_name="albaransheet",
            name="full_read_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Datos extraídos"),
        ),
        migrations.AddField(
            model_name="albaransheet",
            name="bucket_blob",
            field=models.CharField(
                blank=True, max_length=500,
                verbose_name="Archivo en el cubo"),
        ),
    ]
