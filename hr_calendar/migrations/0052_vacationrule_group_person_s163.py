# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0052_vacationrule_group_person_s163.py
# H31 (S163, sesión invasora): reglas de vacaciones por grupo de selección
# y por persona (empresa > grupo > persona; manda la más concreta).
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0229_ack_whatsapp_status_s149"),
        ("hr_calendar", "0051_clockattempt_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="vacationrule",
            name="group",
            field=models.ForeignKey(blank=True, help_text="Regla de los trabajadores de este grupo (y de sus subgrupos) que no tienen días propios.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="vacation_rules", to="document_explorer.persongrouptemplate", verbose_name="Grupo de selección"),
        ),
        migrations.AddField(
            model_name="vacationrule",
            name="person",
            field=models.ForeignKey(blank=True, help_text="Días propios de este trabajador: mandan sobre los de su grupo y los de la empresa.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="vacation_rules", to="document_explorer.personidentity", verbose_name="Trabajador"),
        ),
    ]
