# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0034_correct_estiba_plataformas_domain.py
"""
H30 (S54). Corrección de un bug real de catalogación detectado
durante la auditoría de tipos "sin ningún ejemplo ya clasificado":
ESTIBA_PLATAFORMAS se creó en 0004_seed_closed_vocabulary.py con
domain="PERSONAL", pero la carpeta real donde viven sus archivos es
"DOC. MAQUINAS/PLATAFORMAS (Z)/ESTIBA PLATAFORMAS" -- discrepancia
confirmada con datos reales (9 archivos, Comando S sobre
DocumentIndexEntry).

Miguel Ángel, verbatim, tras subir una ficha de estiba real (ANAPAT)
como ejemplo: "Estos son unos documentos que dependen de cada tipo de
máquina que se carga [...] es una conformidad que el trabajador firma
diciendo que está cumpliendo con la norma y que los puntos de agarre
son exactamente los que indica el fabricante [...] por eso debe de ir
tanto para máquinas, el dominio debe ser machine, y el dominio debe
ser personal, por tanto es both."

Domain correcto confirmado: BOTH (no MACHINE, no PERSONAL) -- el
documento certifica tanto la máquina transportada (amarres según su
tipo/peso) como al trabajador que firma la conformidad.
"""
from django.db import migrations


def correct_domain_to_both(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="ESTIBA_PLATAFORMAS").update(
        domain="BOTH",
    )


def revert_domain_to_personal(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="ESTIBA_PLATAFORMAS").update(
        domain="PERSONAL",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0033_merge_duplicate_types_s51"),
    ]

    operations = [
        migrations.RunPython(correct_domain_to_both, revert_domain_to_personal),
    ]
