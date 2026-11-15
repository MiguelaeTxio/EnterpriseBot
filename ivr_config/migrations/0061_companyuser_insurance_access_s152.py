# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0061_companyuser_insurance_access_s152.py
# S152: `CompanyUser.insurance_access` -- pestaña "Seguros" de
# Documentación. Miguel Ángel: "visible solo para Yolanda y Alejandro
# (y yo)". Se marca a yolanda.bandera, alejandro_sergio y alvarez_admin.

from django.db import migrations, models

INSURANCE_USERNAMES = ("yolanda.bandera", "alejandro_sergio",
                       "alvarez_admin")


def mark_insurance_users(apps, schema_editor):
    """
    Yolanda, Alejandro and Miguel Ángel see the insurance reports.
    ---
    Ven los informes de seguros Yolanda, Alejandro y Miguel Ángel.
    """
    company_user = apps.get_model("ivr_config", "CompanyUser")
    company_user.objects.filter(
        user__username__in=INSURANCE_USERNAMES,
    ).update(insurance_access=True)


def noop(apps, schema_editor):
    """
    Nothing to undo: the column goes away with the field.
    ---
    Nada que deshacer: la columna desaparece con el campo.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0060_companyuser_signature_access_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyuser",
            name="insurance_access",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Puede ver y crear los informes de renovación de "
                    "seguros (pestaña Seguros de Documentación)."
                ),
                verbose_name="Informes de seguros",
            ),
        ),
        migrations.RunPython(mark_insurance_users, noop),
    ]
