# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0136_nomina_vacaciones_registro_jornada_acumulables_s117.py
"""
H31 (S117). Marca NOMINA, VACACIONES y REGISTRO_JORNADA como tipos
acumulables (DocumentTypeCatalog.is_cumulative=True, S107): varias
instancias vigentes A LA VEZ, nunca "solo la más reciente".

Detectado en el dry-run de resolve_vigencia_bidireccional sobre
PERSONAL (EnterpriseBot_002): al no ser acumulables, el recálculo les
aplicaba la regla de "un único vigente por tipo" -- una sola nómina,
un solo parte de vacaciones y un solo registro de jornada por persona.
Miguel Ángel, verbatim: "esos son acumulables, evidentemente. Tanto la
nómina como las vacaciones, como el registro de jornada [...] Y debe de
haber un historial de todas las nóminas."

Además, devuelve a vigente (is_obsolete=False) los documentos de esos
tres tipos que estaban marcados obsoletos: se marcaron con la regla de
"un único vigente por tipo" (backfill S48 y siguientes), que para un
tipo acumulable no aplica -- recuento real antes de esta migración
(consulta de solo lectura, S117): NOMINA 72, REGISTRO_JORNADA 62,
VACACIONES 36. Nunca se tocan archivos ni rutas (4.12), solo el campo.

Reversa: devuelve los tres tipos a is_cumulative=False. Los is_obsolete
restaurados NO se vuelven a marcar (no hay forma fiable de saber cuáles
eran) -- si hiciera falta, resolve_vigencia_bidireccional los
recalcula por fecha.
"""
from django.db import migrations

CUMULATIVE_CODES = ["NOMINA", "VACACIONES", "REGISTRO_JORNADA"]


def mark_cumulative(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=CUMULATIVE_CODES,
    ).update(is_cumulative=True)
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    DocumentIndexEntry.objects.filter(
        document_type__code__in=CUMULATIVE_CODES,
        is_obsolete=True,
    ).update(is_obsolete=False)


def unmark_cumulative(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=CUMULATIVE_CODES,
    ).update(is_cumulative=False)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0135_nombramientos_formato_carta_real_s115"),
    ]

    operations = [
        migrations.RunPython(mark_cumulative, unmark_cumulative),
    ]
