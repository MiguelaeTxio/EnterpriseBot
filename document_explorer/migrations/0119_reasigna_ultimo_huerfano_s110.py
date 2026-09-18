# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0119_reasigna_ultimo_huerfano_s110.py
"""
H36 (S110). Cierre real: unico documento restante de toda la familia
PRL_FORMACION sin persona ni empresa asignada (pk=24138,
"PROCEDIMIENTO DE ACCESO A RECINTO DE CENTRO DE TRABAJO DE GRUAS
ADOLFO ALVAREZ SL"): normativa de acceso al recinto, documento de
empresa como los 941 de 0118, mismo destino (CompanyWorksite id=1,
company="GRUAS").
"""
from django.db import migrations


def reassign(apps, schema_editor):
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    CompanyWorksite = apps.get_model(
        "document_explorer", "CompanyWorksite",
    )
    ContentType = apps.get_model("contenttypes", "ContentType")

    company_ct = ContentType.objects.get(
        app_label="document_explorer", model="companyworksite",
    )
    gruas = CompanyWorksite.objects.get(id=1, company="GRUAS", worksite="")

    n = DocumentIndexEntry.objects.filter(pk=24138).update(
        domain_content_type_id=company_ct.id,
        domain_object_id=gruas.id,
    )
    print("=== ULTIMO HUERFANO REASIGNADO (S110): %d ===" % n)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0118_reasigna_formacion_sin_dueno_a_empresa_s110"),
    ]

    operations = [
        migrations.RunPython(reassign, noop_reverse),
    ]
