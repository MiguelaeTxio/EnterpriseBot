# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0019_service_crane_hours_s131.py
# H30 (S131): horas de grúa en lecturas y revisiones (Miguel Ángel: "si
# tiene grúa, las horas de la grúa de ese camión"). Campos nulos, sin
# valor que rellenar en filas existentes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0018_service_hours_interval_s131'),
    ]

    operations = [
        migrations.AddField(
            model_name='machinemeterreading',
            name='crane_hours',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Horas de grúa'),
        ),
        migrations.AddField(
            model_name='machineservicerecord',
            name='crane_hours',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Horas de grúa en la revisión'),
        ),
    ]
