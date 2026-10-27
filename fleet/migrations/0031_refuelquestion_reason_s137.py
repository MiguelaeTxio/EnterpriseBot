# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0031_refuelquestion_reason_s137.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0030_service_record_engine_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="refuelquestion",
            name="reason",
            field=models.CharField(
                blank=True, max_length=255,
                verbose_name="Por qué se pregunta"),
        ),
    ]
