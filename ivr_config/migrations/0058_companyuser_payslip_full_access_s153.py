# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0058_companyuser_payslip_full_access_s153.py
# S153 (H24, nóminas): `CompanyUser.payslip_full_access` -- ve, descarga y
# envía todas las entregas de nóminas sin que se las compartan. Miguel
# Ángel: "Tendrá acceso única y exclusivamente Alejandro a todas". Se
# marca a la cuenta de Alejandro (usuario alejandro_sergio).

from django.db import migrations, models

FULL_ACCESS_USERNAMES = ("alejandro_sergio",)


def grant_full_access(apps, schema_editor):
    """
    Full payslip access for Alejandro's account.
    ---
    Acceso a todas las nóminas para la cuenta de Alejandro.
    """
    company_user = apps.get_model("ivr_config", "CompanyUser")
    company_user.objects.filter(
        user__username__in=FULL_ACCESS_USERNAMES,
    ).update(payslip_full_access=True)


def noop(apps, schema_editor):
    """
    Nothing to undo: the column goes away with the field.
    ---
    Nada que deshacer: la columna desaparece con el campo.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0057_role_sales_s148"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyuser",
            name="payslip_full_access",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Ve, descarga y envía todas las entregas de nóminas "
                    "sin que se las compartan. El resto de usuarios solo "
                    "ve las que sube y las que le comparte quien las sube."
                ),
                verbose_name="Acceso a todas las nóminas",
            ),
        ),
        migrations.RunPython(grant_full_access, noop),
    ]
