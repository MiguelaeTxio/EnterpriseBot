# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0075_reenganchar_poliza_rc_grupo_s96.py
"""
H31 (S96). Corrige el vinculo real de DocumentIndexEntry pk=12783
("CERT. COBERTURAS + POLIZA 15-12-2023 POL 3RG427000498 GRUAS ADOLFO
ALVAREZ.pdf", document_type=POLIZA_SEGURO), detectado durante la
auditoria de fechado de H31: estaba enlazado a
domain_content_type=PersonIdentity, domain_object_id=4 (Adolfo
Alvarez Diaz, dueno) pese a que el documento real, verificado por
contenido (descarga directa del blob, nunca por heuristica de
nombre ni carpeta), es un certificado de Responsabilidad Civil de
GRUAS ADOLFO ALVAREZ, S.L. como empresa -- tomador y asegurado la
propia sociedad (CIF B29405040), cobertura de toda la actividad de
alquiler de maquinaria del grupo, no un documento personal de
Adolfo Alvarez Diaz ni de una maquina concreta. Mismo patron exacto
que el incidente real de CERTIFICADO_PODERES en S95.

Miguel Angel, verbatim, confirmando el dominio real: "pk=12783 es un
documento COMPANY". Reenganchado a CompanyWorksite pk=1
(company='GRUAS', worksite='') -- fila real ya existente para
"empresa, sin obra concreta", confirmada contra BD real (Comando S
EnterpriseBot_008_GET.txt) antes de reutilizarla, nunca creada de
cero sin verificar que ya existiera la fila correcta.

domain_object_id es un PositiveBigIntegerField generico (GenericForeignKey) --
no es una FK real, así que este cambio no requiere ninguna migración
de esquema, solo el ContentType correcto + el pk correcto en las dos
columnas.
"""
from django.db import migrations


def relink_to_company(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    ct_company_worksite = ContentType.objects.get(
        app_label="document_explorer", model="companyworksite",
    )
    DocumentIndexEntry.objects.filter(pk=12783).update(
        domain_content_type=ct_company_worksite,
        domain_object_id=1,
    )


def revert_to_person(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    ct_person_identity = ContentType.objects.get(
        app_label="document_explorer", model="personidentity",
    )
    DocumentIndexEntry.objects.filter(pk=12783).update(
        domain_content_type=ct_person_identity,
        domain_object_id=4,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0074_documenttypecatalog_dating_scope_s96"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(relink_to_company, revert_to_person),
    ]
