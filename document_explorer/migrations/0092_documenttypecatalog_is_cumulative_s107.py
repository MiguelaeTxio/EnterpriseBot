# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0092_documenttypecatalog_is_cumulative_s107.py
"""
H35 (S107). Campo nuevo `DocumentTypeCatalog.is_cumulative` -- ver
docstring completo en models.py. Origen: pase de control real tras
H35 (backfill_obsolete_duplicates en dry-run, 197 grupos/170
documentos) que reveló que agrupar "mas de un vigente" solo por
tipo+persona, sin distinguir, marcaria como obsoletos cursos de
FORMACION/ENTREGA_INFORMACION reales y distintos entre si -- decision
explicita de Miguel Angel de anadir el campo en vez de parchear el
backfill puntualmente, para reutilizarlo tambien en las subplantillas
de dosier (H31).

Siembra: True para los tipos "de evento repetible" confirmados en
S107 (familia PRL_FORMACION casi entera, mas ENTREGA_DOCUMENTACION_
VARIA/ENTREGA_MOVIL de ADMINISTRATIVO). Todo lo demas queda en el
default False ("de identidad/renovable", un vigente por persona) --
nunca se toca sin evidencia real, mismo criterio de siempre.
"""
from django.db import migrations, models

CUMULATIVE_CODES = [
    "CURSO", "ENTREGA_INFORMACION", "ENTREGA_MANUAL_COMBUSTIBLE",
    "ENTREGA_PROTOCOLO_AUXILIO_CARRETERA", "EPIS", "ESTIBA_PLATAFORMAS",
    "EVALUACION_RIESGO", "FORMACION", "FORMACION_ITC_MINERA",
    "FORMACION_PRL_GENERICA", "FORMACION_PRL_MAQUINARIA",
    "INFORMACION_MEDIDAS_PROTECCION", "NOMBRAMIENTO_JEFE_MANIOBRAS",
    "NOMBRAMIENTO_RECURSO_PREVENTIVO", "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD",
    "PLAN_ACTUACION_CALOR", "RECURSO_PREVENTIVO",
    "AUTORIZACION_USO_MAQUINARIA", "CAPACITACION",
    "ENTREGA_DOCUMENTACION_VARIA", "ENTREGA_MOVIL",
]


def seed_cumulative(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=CUMULATIVE_CODES,
    ).update(is_cumulative=True)


def unseed_cumulative(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=CUMULATIVE_CODES,
    ).update(is_cumulative=False)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0091_seed_comunicacion_inspeccion_trabajo_s107"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="is_cumulative",
            field=models.BooleanField(
                default=False,
                verbose_name="Acumulable (varios vigentes a la vez)",
                help_text=(
                    "H35 (S107). Distinto de dating_scope (esa decide si hace "
                    "falta fecha en cada instancia; esta decide si varias "
                    "instancias del mismo tipo pueden ser vigentes A LA VEZ, "
                    "sin que una sustituya a la otra). False (defecto): tipo "
                    "'de identidad/renovable' -- DNI, CARNET_CONDUCIR, "
                    "CONTRATO, RECONOCIMIENTO_MEDICO... -- solo puede haber "
                    "un documento vigente por persona, evaluate_substitution() "
                    "marca el resto is_obsolete. True: tipo 'de evento "
                    "repetible' -- FORMACION, ENTREGA_INFORMACION, EPIS... -- "
                    "una persona puede tener varios documentos reales y "
                    "vigentes a la vez (cursos distintos, entregas distintas); "
                    "el backfill/sustitución automática NUNCA debe agrupar "
                    "estos solo por tipo+persona sin más. Dentro de un tipo "
                    "acumulable, dos instancias SÍ compiten entre sí cuando "
                    "son literalmente el mismo curso/evento repetido (p. ej. "
                    "una recertificación que sustituye a la anterior) -- ese "
                    "emparejamiento por curso/evento concreto queda pendiente "
                    "de construir (no hay campo estructurado de 'curso' todavía "
                    "en DocumentIndexEntry), por eso el backfill de S107 excluye "
                    "los tipos acumulables por completo en vez de adivinar. "
                    "Decisión explícita de Miguel Ángel (S107): mismo campo "
                    "reutilizable para las subplantillas de dosier (H31) -- "
                    "una plantilla como 'Sacyr' podrá tener una subplantilla "
                    "de formación donde se marquen varios tipos de curso a "
                    "incluir, precisamente porque son acumulables."
                ),
            ),
        ),
        migrations.RunPython(seed_cumulative, unseed_cumulative),
    ]
