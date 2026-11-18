# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0062_section_attention_schedule_s155.py
# S155: `Section.attention_schedule` -- horario de atención de la
# centralita elegido entre los horarios de jornada (Miguel Ángel: "lo
# dejamos solamente en los horarios que tengamos en horarios de
# jornada"). Nulo: las franjas antiguas (SectionSchedule) se siguen
# usando mientras la sección no tenga horario elegido.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0061_companyuser_insurance_access_s152"),
    ]

    operations = [
        migrations.AddField(
            model_name="section",
            name="attention_schedule",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Horario de jornada en el que la centralita da la sección "
                    "por abierta. Sin «Horario distinto según el día», de "
                    "lunes a viernes. No cuenta si la sección es 24 horas."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attention_sections",
                to="ivr_config.workdayschedule",
                verbose_name="Horario de atención",
            ),
        ),
    ]
