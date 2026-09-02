# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/extract_birth_dates_from_dni.py
"""
H30 (S83). Punto 3 de la hoja de ruta: rellena `PersonIdentity.
birth_date` para el resto de los ~78 activos que todavia no lo tienen
(el campo se añadio en S82, migracion 0067, solo con valor real para
Estevao Veloso Sampaio hasta ahora).

Ninguna lectura nueva: reutiliza `extract_dni_mrz_birthdate()` de
`date_verification_service.py` (S83) sobre el `ocr_text` YA CACHEADO
de los documentos DNI/NIE de cada persona -- el bloque critico de
fechas (que incluye DNI) ya quedo cerrado en S80, asi que el texto ya
deberia estar disponible sin volver a tocar GCS ni Tesseract. Coste de
CPU minimo (regex sobre texto ya guardado), seguro en la consola Bash
de PythonAnywhere.

CORREGIDO EN S84 -- BUG REAL DE ORIGEN (S83): la version original
localizaba el documento DNI de cada persona por `parent_path` bajo el
`folder_path` de `PersonIdentity` (comparacion de texto de carpeta).
Miguel Angel, verbatim, al detectarlo: "si se trata de que todo viva
en la base de datos, que coño me estas contando de carpeta [...] me
da igual en que carpeta este [...] mientras la base de datos sepa
donde esta el documento, el documento tiene que estar asignado a su
persona en base de datos." Es exactamente el objetivo del propio H30
(seccion 1 del anexo): el vinculo real y vivo es
`DocumentIndexEntry.domain_content_type`/`domain_object_id` (el mismo
`GenericForeignKey` ya usado por el resto de servicios de H30), nunca
la ruta de carpeta -- que puede desalinearse sin que eso signifique
que el documento no esta vinculado. Caso real que disparo el hallazgo:
Julio Alberto Rueda Escudero (76883782A) tenia su DNI perfectamente
vinculado en BD (`domain_object_id` correcto, `ocr_text` cacheado, 423
caracteres) pero el `parent_path` real de su documento no empezaba por
su `folder_path` -- el comando lo reportaba como "SIN DOCUMENTO DNI"
siendo falso.

Localizacion del documento DNI de cada persona: por
`domain_content_type`/`domain_object_id` (el vinculo real de BD),
nunca por carpeta ni por nombre de archivo. Entre varios documentos
DNI de la misma persona (historico + vigente), se usa el primero cuyo
MRZ valide -- la fecha de nacimiento es la misma en todos los DNIs
reales de una persona, asi que no hace falta elegir "el mas reciente"
como si fuera caducidad.

DRY-RUN POR DEFECTO. --apply escribe de verdad. --limit acota una
pasada de muestreo antes de escalar (mismo principio de verificacion
previa de todo el proyecto).
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.date_verification_service import extract_dni_mrz_birthdate
from document_explorer.models import DocumentIndexEntry, PersonIdentity


class Command(BaseCommand):
    help = (
        "H30 S83 -- rellena PersonIdentity.birth_date desde el MRZ de "
        "documentos DNI/NIE ya indexados (ocr_text cacheado). "
        "Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Acota a los N primeros activos sin birth_date -- "
                 "muestra de verificacion antes de escalar.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]

        person_ct = ContentType.objects.get_for_model(PersonIdentity)

        personas = PersonIdentity.objects.filter(
            is_active_employee=True, birth_date__isnull=True,
        ).order_by("id")
        if limit:
            personas = personas[:limit]

        stats = {
            "total_candidatos": personas.count() if not limit else len(personas),
            "resueltos": 0,
            "sin_documento_dni": 0,
            "sin_mrz_valido": 0,
        }

        for persona in personas:
            docs = DocumentIndexEntry.objects.filter(
                domain_content_type=person_ct,
                domain_object_id=persona.id,
                document_type__code__in=["DNI", "NIE"],
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            ).exclude(ocr_text__in=["", None]).order_by("id")

            if not docs.exists():
                stats["sin_documento_dni"] += 1
                self.stdout.write(
                    "SIN DOCUMENTO DNI: %s (dni=%s, sin DocumentIndexEntry "
                    "DNI/NIE vinculado en BD, no por carpeta)"
                    % (persona, persona.dni)
                )
                continue

            birth_date = None
            source_doc = None
            for doc in docs:
                birth_date = extract_dni_mrz_birthdate(doc.ocr_text)
                if birth_date:
                    source_doc = doc
                    break

            if not birth_date:
                stats["sin_mrz_valido"] += 1
                self.stdout.write(
                    "SIN MRZ VALIDO: %s -- %d documento(s) DNI/NIE "
                    "revisado(s), ninguno con MRZ que valide"
                    % (persona, docs.count())
                )
                continue

            stats["resueltos"] += 1
            self.stdout.write(
                "%s  %s  ->  birth_date=%s  [%s]"
                % (
                    "APLICADO" if apply_changes else "CANDIDATO",
                    persona, birth_date.isoformat(), source_doc.name,
                )
            )
            if apply_changes:
                persona.birth_date = birth_date
                persona.save(update_fields=["birth_date"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
