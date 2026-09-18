# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0112_reclassify_from_cached_ocr_text_3_s110.py
"""
H36 (S110). Reclasifica y fecha los documentos que siguen en los 5
cajones genericos (FORMACION, CURSO, CARNET_GRUISTA,
FORMACION_ITC_MINERA, FORMACION_PRL_MAQUINARIA) usando el `ocr_text`
YA CACHEADO en base de datos -- sin descargar nada de Storage, sin
llamar a Cloud Vision, sin la VM de OCR. Hallazgo real de esta misma
sesion (Miguel Angel): cada relanzamiento del script de la VM
repetia OCR completo sobre los mismos documentos solo para probar una
senal nueva, un coste real evitable ahora que el texto ya esta
cacheado de las pasadas anteriores.

Reutiliza exactamente la misma logica de resolucion de tipo
(`personal_content_classification.resolve_type_from_content`, el
mismo diccionario CONTENT_SIGNALS/CONTENT_WINS que usan tambien la VM
y `run_personal_retype_and_date`) y de fecha por contexto
(`date_verification_service.classify_dates_in_text`, sin el fallback
de Gemini -- ninguno de estos 5 tipos tiene ocr_unreliable=True).

Solo escribe fecha en el campo que este vacio -- nunca sobreescribe
una fecha ya resuelta en una pasada anterior. Nunca retipa si el
resultado es ambiguo (mismo criterio que el resto de esta sesion,
queda para revision manual). Imprime un resumen real al final,
visible en el log del propio paso de despliegue (GitHub Actions).
"""
from django.db import migrations

RETYPE_CODES = [
    "FORMACION", "CURSO", "CARNET_GRUISTA",
    "FORMACION_ITC_MINERA", "FORMACION_PRL_MAQUINARIA",
]


def reclassify_from_cache(apps, schema_editor):
    from document_explorer.personal_content_classification import (
        _strip_accents, resolve_type_from_content,
    )
    from document_explorer.date_verification_service import (
        classify_dates_in_text,
    )

    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    PersonIdentity = apps.get_model(
        "document_explorer", "PersonIdentity",
    )

    type_id_by_code = dict(
        DocumentTypeCatalog.objects.filter(is_active=True)
        .values_list("code", "id"),
    )
    code_by_type_id = {v: k for k, v in type_id_by_code.items()}

    birth_dates = dict(
        PersonIdentity.objects.filter(is_active_employee=True)
        .exclude(birth_date__isnull=True)
        .values_list("id", "birth_date"),
    )

    qs = DocumentIndexEntry.objects.filter(
        document_type_id__in=[
            type_id_by_code[c] for c in RETYPE_CODES if c in type_id_by_code
        ],
        deleted_at__isnull=True,
        purged_at__isnull=True,
    ).exclude(ocr_text__isnull=True).exclude(ocr_text="")

    stats = {
        "retipados": 0, "fecha_puesta": 0, "ambiguos": 0,
        "sin_texto_util": 0, "sin_cambio": 0,
    }

    for entry in qs.iterator():
        raw_text = entry.ocr_text or ""
        if len(raw_text.strip()) < 20:
            stats["sin_texto_util"] += 1
            continue

        text_upper = _strip_accents(raw_text).upper()
        current_code = code_by_type_id.get(entry.document_type_id)
        new_code, is_ambiguous, matched = resolve_type_from_content(
            text_upper, current_code,
        )

        if is_ambiguous:
            stats["ambiguos"] += 1
            continue

        changed = False

        if new_code and new_code != current_code and new_code in type_id_by_code:
            entry.document_type_id = type_id_by_code[new_code]
            changed = True

        bad_dates = set()
        birth_date = birth_dates.get(entry.domain_object_id)
        if birth_date:
            bad_dates = {
                birth_date,
                birth_date.replace(year=birth_date.year + 100),
            }

        expiry, issue, other = classify_dates_in_text(raw_text)
        date_field, date_value = None, None
        if expiry:
            date_field, date_value = "expiry_date", expiry
        elif issue:
            date_field, date_value = "issue_date", issue
        elif len(other) == 1:
            date_field, date_value = "issue_date", other[0]
        if date_value in bad_dates:
            date_field, date_value = None, None

        if date_value:
            if date_field == "expiry_date" and entry.expiry_date is None:
                entry.expiry_date = date_value
                changed = True
                stats["fecha_puesta"] += 1
            elif date_field == "issue_date" and entry.issue_date is None:
                entry.issue_date = date_value
                changed = True
                stats["fecha_puesta"] += 1

        if changed:
            if new_code and new_code != current_code:
                stats["retipados"] += 1
            entry.save()
        else:
            stats["sin_cambio"] += 1

    print(
        "=== RECLASIFICACION DESDE OCR CACHEADO (S110) ===\n"
        "    retipados: %(retipados)d\n"
        "    fecha_puesta: %(fecha_puesta)d\n"
        "    ambiguos: %(ambiguos)d\n"
        "    sin_texto_util: %(sin_texto_util)d\n"
        "    sin_cambio: %(sin_cambio)d" % stats
    )


def noop_reverse(apps, schema_editor):
    # Reversion real no tiene sentido aqui (no hay forma de saber que
    # documentos volver a dejar en su tipo generico anterior sin
    # guardar un log completo del estado previo) -- migracion de solo
    # avance, documentado explicitamente.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0111_seed_gwo_avsec_s110"),
    ]

    operations = [
        migrations.RunPython(reclassify_from_cache, noop_reverse),
    ]
