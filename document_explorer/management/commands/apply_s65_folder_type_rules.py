# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/apply_s65_folder_type_rules.py
"""
H30 (S65). Aplica 5 reglas carpeta->tipo confirmadas con muestra real
(una a tres muestras por carpeta, contenido leido letra por letra,
nunca asumido por nombre de carpeta -- ver anexo, bloque "HOJA DE RUTA
PARA LA SIGUIENTE SESION (S65)"). Mismo patron que
apply_formacion_folder_default.py: solo actua sobre
document_type__isnull=True, nunca sobreescribe un tipo ya resuelto.

Rutas reales verificadas contra produccion (EnterpriseBot_002_GET.txt,
S65) antes de escribir este comando -- ninguna se asumio por el texto
del anexo. En particular AUTORIZACION MEDIOS DE COMUNICACION vive en
"DOC. PERSONAL/PERSONAL/AUTORIZACION MEDIOS DE COMUNICACION/", no en
"DOC. PERSONAL/AUTORIZACION MEDIOS DE COMUNICACION/" como sugeria el
anexo -- verificarlo evito escribir una regla que no habria encontrado
ningun archivo real.

DECISION DELIBERADA -- AUTORIZACION_LIBRO_SUBCONTRATA NUNCA RESUELVE
DOMINIO POR CARPETA/NOMBRE. Confirmado con 3 muestras reales en S65
que el nombre de archivo de esta carpeta NO es fiable para identificar
a la persona autorizada (el documento cita dos personas -- el
administrador que firma y el trabajador autorizado -- y el nombre de
archivo a veces corresponde al administrador, a veces a un tercero sin
relacion, ej. "Autorizacion_ALVAREZ_GEA.docx" autoriza en realidad a
Jose Carlos Martinez Segura). Resolver este dominio requiere leer el
cuerpo real del texto ("A D. ___ con DNI: ___"), tarea de Fase B
(OCR/lectura real), nunca de este barrido de Fase A. Por eso esta
carpeta, a diferencia de las otras 4, NUNCA llama a los resolvers de
persona -- queda siempre con dominio pendiente, sin excepcion.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.management.commands.calibrate_fase_a_keywords import (
    BUCKET,
)
from document_explorer.management.commands.run_fase_a_sweep import (
    _build_person_name_index, _resolve_person_by_folder,
    _resolve_person_by_name, _resolve_person_by_sliding_window,
)
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)

# (ruta real bajo DOC. PERSONAL, codigo de tipo, resolver dominio)
FOLDER_RULES = [
    (
        "DOC. PERSONAL/ENTREGA MANUAL COMBUSTIBLE",
        "ENTREGA_MANUAL_COMBUSTIBLE",
        True,
    ),
    (
        "DOC. PERSONAL/PERSONAL/AUTORIZACIÓN MEDIOS DE COMUNICACIÓN",
        "AUTORIZACION_MEDIOS_COMUNICACION",
        True,
    ),
    (
        "DOC. PERSONAL/ENTREGA DE EVALUACION DE RIESGO",
        "EVALUACION_RIESGO",
        True,
    ),
    (
        "DOC. PERSONAL/AUTORIZACION FIRMA LIBRO DE SUBCONTRATA",
        "AUTORIZACION_LIBRO_SUBCONTRATA",
        False,  # NUNCA resolver persona -- ver docstring
    ),
    (
        "DOC. PERSONAL/RENOVACION CARNE DEGRUISTA",
        "CARNET_GRUISTA",
        True,
    ),
]


class Command(BaseCommand):
    help = (
        "H30 S65: aplica las 5 reglas carpeta->tipo confirmadas con "
        "muestra real sobre lo que quede sin tipo en cada una. "
        "Dry-run por defecto, usar --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        person_name_index = _build_person_name_index()

        self.stdout.write("=== %s ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))

        for root_path, type_code, resolve_domain in FOLDER_RULES:
            try:
                doc_type = DocumentTypeCatalog.objects.get(code=type_code)
            except DocumentTypeCatalog.DoesNotExist:
                self.stderr.write(
                    "SALTADA (%s): el codigo %r no existe en "
                    "DocumentTypeCatalog -- revisar migracion 0043 "
                    "antes de reintentar." % (root_path, type_code)
                )
                continue

            qs = DocumentIndexEntry.objects.filter(
                Q(parent_path=root_path)
                | Q(parent_path__startswith=root_path + "/"),
                bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                document_type__isnull=True,
                deleted_at__isnull=True, purged_at__isnull=True,
            ).only("id", "name", "parent_path")

            stats = {
                "asignados_con_persona": 0,
                "asignados_dominio_pendiente": 0,
            }
            total_count = qs.count()

            for entry in qs:
                obj = None
                if resolve_domain:
                    obj = _resolve_person_by_folder(entry)
                    if not obj:
                        obj = _resolve_person_by_name(
                            entry, person_name_index,
                        )
                    if not obj:
                        obj = _resolve_person_by_sliding_window(
                            entry, person_name_index,
                        )

                if obj:
                    stats["asignados_con_persona"] += 1
                else:
                    stats["asignados_dominio_pendiente"] += 1

                if apply_changes:
                    entry.document_type = doc_type
                    if obj:
                        entry.domain_content_type = person_ct
                        entry.domain_object_id = obj.pk
                        entry.save(update_fields=[
                            "document_type", "domain_content_type",
                            "domain_object_id",
                        ])
                    else:
                        entry.save(update_fields=["document_type"])

            self.stdout.write(
                "-- %s -> %s (resolver_dominio=%s): "
                "asignados_con_persona=%d, "
                "asignados_dominio_pendiente=%d, total=%d" % (
                    root_path, type_code, resolve_domain,
                    stats["asignados_con_persona"],
                    stats["asignados_dominio_pendiente"],
                    total_count,
                )
            )
