# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0028_gasogesuser_ask_driver_s137.py
# H30 (S137): a quién se pregunta por WhatsApp se decide también por
# chófer. Campo nuevo con valor por defecto (todos sí, como hasta
# ahora); sin datos que mover.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0027_service_record_from_work_order_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasogesuser",
            name="ask_driver",
            field=models.BooleanField(
                default=True,
                help_text="Si no, no se le pregunta por sus repostajes.",
                verbose_name="Se le pregunta por WhatsApp",
            ),
        ),
    ]
