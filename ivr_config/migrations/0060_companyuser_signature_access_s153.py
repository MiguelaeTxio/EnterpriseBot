# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0060_companyuser_signature_access_s153.py
# S153: `CompanyUser.signature_access` -- pestaña "Firmas" de
# Documentación. Miguel Ángel: "A esto solamente puede tener acceso
# Yolanda." Se marca a yolanda.bandera y a alvarez_admin (pruebas).

from django.db import migrations, models

SIGNATURE_USERNAMES = ("yolanda.bandera", "alvarez_admin")


def mark_signature_users(apps, schema_editor):
    """
    Yolanda and Miguel Ángel (tests) manage the signatures.
    ---
    Gestionan las firmas Yolanda y Miguel Ángel (pruebas).
    """
    company_user = apps.get_model("ivr_config", "CompanyUser")
    company_user.objects.filter(
        user__username__in=SIGNATURE_USERNAMES,
    ).update(signature_access=True)


def noop(apps, schema_editor):
    """
    Nothing to undo: the column goes away with the field.
    ---
    Nada que deshacer: la columna desaparece con el campo.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0059_companyuser_payslip_uploader_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyuser",
            name="signature_access",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Puede guardar las firmas de las empresas y generar "
                    "con ellas los documentos firmados (pestaña Firmas de "
                    "Documentación)."
                ),
                verbose_name="Firmas de empresa",
            ),
        ),
        migrations.RunPython(mark_signature_users, noop),
    ]
