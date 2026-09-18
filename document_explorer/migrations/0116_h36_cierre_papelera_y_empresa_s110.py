# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0116_h36_cierre_papelera_y_empresa_s110.py
"""
H36 (S110). Cierre final, criterio explicito de Miguel Angel (verbatim,
resumido): "si son documentos de trabajadores inactivos, a papelera.
Si son documentos de empresa, a empresa. Si son cursos que no estan
dentro del Excel [de Yolanda] -- mas los dos que no estaban, mineria y
maquinaria -- eso todo a papelera y terminamos."

Cuatro acciones, en este orden:

1. Papelera (deleted_at, nunca purged_at -- reversible) para TODOS los
   documentos activos hoy tipados FORMACION_ITC_MINERA o
   FORMACION_PRL_MAQUINARIA, cualquier estado del trabajador: son los
   "dos grupos grandes" que nunca fueron columna real del Excel de
   Yolanda, a diferencia de los otros 15 tipos de FORMACION_* que si
   se confirmaron uno a uno contra su Excel real esta misma sesion.

2. Papelera para todo FORMACION/CURSO (los dos cajones genericos) que
   cuelgue de un trabajador con is_active_employee=False -- nunca
   tocados en el resto de esta sesion (todo el barrido de retipado
   fue explicitamente solo sobre activos), ahora se cierran igual.

3. Reasignacion a CompanyWorksite (dominio EMPRESA) de los documentos
   reales de nivel empresa encontrados en la revision completa de
   FORMACION/CURSO -- nunca deberian haber colgado de una persona:
   - pk=25089: "Informe empresa 2017" (Fundacion Estatal), TRANSGRUAL.
   - pk=25189/25190: "Informacion a la Representacion Legal de los
     Trabajadores (Acciones Formativas de las Empresas)", TRANSGRUAL.
   - pk=26002: "ANEXO II Solicitud de participacion" (plan de
     formacion a nivel empresa), TRANSGRUAL.
   Se reasignan al CompanyWorksite id=2 (company="TRANSGRUAL",
   worksite="") ya existente, con el tipo CONVENIO_FORMACION_BONIFICADA
   (domain=COMPANY, ya sembrado en 0097, sin uso real hasta ahora).

4. Papelera para el resto de FORMACION/CURSO restantes en trabajadores
   ACTIVOS tras las 6 pasadas de reclasificacion de esta sesion: cursos
   sueltos de un solo proveedor, boletines/facturas/justificantes y
   papeleo de plantilla FLC/Fundacion Estatal que no corresponde a
   ninguna de las 15 columnas reales del Excel -- quedan fuera del
   alcance de seguimiento, decision explicita de Miguel Angel de no
   seguir persiguiendolos uno a uno.
"""
from django.db import migrations
from django.utils import timezone

TRASH_TYPE_CODES = ["FORMACION_ITC_MINERA", "FORMACION_PRL_MAQUINARIA"]
GENERIC_TYPE_CODES = ["FORMACION", "CURSO"]

COMPANY_REASSIGN_IDS = [25089, 25189, 25190, 26002]


def close_h36(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    PersonIdentity = apps.get_model(
        "document_explorer", "PersonIdentity",
    )
    CompanyWorksite = apps.get_model(
        "document_explorer", "CompanyWorksite",
    )
    ContentType = apps.get_model("contenttypes", "ContentType")

    now = timezone.now()
    stats = {
        "papelera_itc_maquinaria": 0,
        "papelera_inactivos": 0,
        "reasignados_empresa": 0,
        "papelera_resto_activos": 0,
    }

    person_ct = ContentType.objects.get(
        app_label="document_explorer", model="personidentity",
    )
    company_ct = ContentType.objects.get(
        app_label="document_explorer", model="companyworksite",
    )

    type_id_by_code = dict(
        DocumentTypeCatalog.objects.filter(is_active=True)
        .values_list("code", "id"),
    )

    # 1. FORMACION_ITC_MINERA / FORMACION_PRL_MAQUINARIA -- todos, sin
    # filtrar por activo/inactivo.
    trash_type_ids = [
        type_id_by_code[c] for c in TRASH_TYPE_CODES if c in type_id_by_code
    ]
    n = (
        DocumentIndexEntry.objects.filter(
            document_type_id__in=trash_type_ids,
            deleted_at__isnull=True,
        )
        .update(deleted_at=now)
    )
    stats["papelera_itc_maquinaria"] = n

    # 2. FORMACION/CURSO de trabajadores inactivos.
    generic_type_ids = [
        type_id_by_code[c] for c in GENERIC_TYPE_CODES if c in type_id_by_code
    ]
    inactive_person_ids = list(
        PersonIdentity.objects.filter(is_active_employee=False)
        .values_list("id", flat=True),
    )
    n = (
        DocumentIndexEntry.objects.filter(
            document_type_id__in=generic_type_ids,
            domain_content_type_id=person_ct.id,
            domain_object_id__in=inactive_person_ids,
            deleted_at__isnull=True,
        )
        .update(deleted_at=now)
    )
    stats["papelera_inactivos"] = n

    # 3. Reasignacion a empresa (TRANSGRUAL, CompanyWorksite id=2).
    try:
        transgrual = CompanyWorksite.objects.get(
            id=2, company="TRANSGRUAL", worksite="",
        )
        convenio_type_id = type_id_by_code.get("CONVENIO_FORMACION_BONIFICADA")
    except CompanyWorksite.DoesNotExist:
        transgrual = None
        convenio_type_id = None

    if transgrual and convenio_type_id:
        n = (
            DocumentIndexEntry.objects.filter(
                id__in=COMPANY_REASSIGN_IDS,
                deleted_at__isnull=True,
            )
            .update(
                domain_content_type_id=company_ct.id,
                domain_object_id=transgrual.id,
                document_type_id=convenio_type_id,
            )
        )
        stats["reasignados_empresa"] = n

    # 4. Resto de FORMACION/CURSO en activos -- papelera.
    n = (
        DocumentIndexEntry.objects.filter(
            document_type_id__in=generic_type_ids,
            deleted_at__isnull=True,
        )
        .exclude(id__in=COMPANY_REASSIGN_IDS)
        .update(deleted_at=now)
    )
    stats["papelera_resto_activos"] = n

    print(
        "=== CIERRE H36 (S110) ===\n"
        "    papelera_itc_maquinaria: %(papelera_itc_maquinaria)d\n"
        "    papelera_inactivos: %(papelera_inactivos)d\n"
        "    reasignados_empresa: %(reasignados_empresa)d\n"
        "    papelera_resto_activos: %(papelera_resto_activos)d" % stats
    )


def noop_reverse(apps, schema_editor):
    # Reversion real no tiene sentido (deleted_at masivo no distingue
    # cual de las 4 acciones puso cada fecha) -- migracion de solo
    # avance, documentado explicitamente. El papelereo es reversible a
    # mano (deleted_at=NULL) documento a documento si hiciera falta.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0115_reclassify_from_cached_ocr_text_6_s110"),
    ]

    operations = [
        migrations.RunPython(close_h36, noop_reverse),
    ]
