# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/migrations/0002_cae_demand_links_s156.py
"""
S156. Cada documento pedido enlazado a su tipo del catálogo y a su
empresa, trabajador o centro de gasto; el aviso, con quién lo atendió.
Los avisos ya leídos vuelven a PENDIENTE para leerse otra vez con el
catálogo (el barrido los reencola).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def reread_mails(apps, schema_editor):
    CaeMail = apps.get_model("cae_mail", "CaeMail")
    CaeMail.objects.filter(status="PROCESSED").update(status="PENDING")


class Migration(migrations.Migration):

    dependencies = [
        ("cae_mail", "0001_initial_s156"),
        ("document_explorer", "0232_company_requirements_dossier_scope_s156"),
        ("fleet", "0045_qr_editor_settings_s154"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="caedemand",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="document_explorer.companyfiscalprofile",
                verbose_name="Empresa del grupo",
            ),
        ),
        migrations.AddField(
            model_name="caedemand",
            name="document_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="document_explorer.documenttypecatalog",
                verbose_name="Tipo documental",
            ),
        ),
        migrations.AddField(
            model_name="caedemand",
            name="machine",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="fleet.machineasset",
                verbose_name="Centro de gasto",
            ),
        ),
        migrations.AddField(
            model_name="caedemand",
            name="person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="document_explorer.personidentity",
                verbose_name="Trabajador",
            ),
        ),
        migrations.AddField(
            model_name="caemail",
            name="attended_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Atendido el"
            ),
        ),
        migrations.AddField(
            model_name="caemail",
            name="attended_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Atendido por",
            ),
        ),
        migrations.RunPython(reread_mails, migrations.RunPython.noop),
    ]
