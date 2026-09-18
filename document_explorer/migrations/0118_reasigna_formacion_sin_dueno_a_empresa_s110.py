# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0118_reasigna_formacion_sin_dueno_a_empresa_s110.py
"""
H36 (S110). Los 941 documentos FORMACION/CURSO con
domain_content_type_id IS NULL (encontrados al restaurar en 0117) no
son de personal ni de maquinaria -- viven en carpetas compartidas de
infraestructura de formacion de la empresa (DOC. PERSONAL/FORMACION
TRABAJADORES/ANAPAT/, DOC. PERSONAL/ENTREGA EPIS/EPIS VARIAS
EMPRESAS/): acreditaciones ANAPAT, normas UNE, fotos de la campa,
plantillas de gestion documental. Nunca estuvieron dentro del alcance
de H36 (el anexo de apertura, S109, solo contaba documentos ya
ligados a una PersonIdentity: 1.182 activos + 414 inactivos).

Decision explicita de Miguel Angel: van a empresa, sin retocar tipo
ni nada mas -- se reasigna unicamente domain_content_type/
domain_object_id al CompanyWorksite id=1 (company="GRUAS",
worksite=""), que ya existe y es el nivel de empresa general
correcto para papeleo de infraestructura compartida, no ligado a un
cliente/obra concreto.
"""
from django.db import migrations


def reassign_to_company(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
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

    type_ids = list(
        DocumentTypeCatalog.objects.filter(
            code__in=["FORMACION", "CURSO"],
        ).values_list("id", flat=True),
    )

    n = (
        DocumentIndexEntry.objects.filter(
            document_type_id__in=type_ids,
            domain_content_type_id__isnull=True,
        )
        .update(
            domain_content_type_id=company_ct.id,
            domain_object_id=gruas.id,
        )
    )

    print(
        "=== REASIGNACION A EMPRESA (S110) ===\n"
        "    reasignados_gruas: %d" % n
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0117_fix_0116_restaura_sin_dueno_s110"),
    ]

    operations = [
        migrations.RunPython(reassign_to_company, noop_reverse),
    ]
