# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/management/commands/attach_delivery_note_photo.py
"""
Adjunta una foto/PDF histórica a un DeliveryNote ya existente en BD
que se quedó sin archivo asociado ("huérfano de foto") -- caso real
de S015: 7-8 albaranes procesados por correo electrónico mientras se
decidía entre M365/Google Drive para la persistencia de archivos,
antes de que existiera spare_parts.gdrive_service. Sus datos ya están
extraídos y confirmados (status=ASSIGNED) -- este comando SOLO asigna
el archivo, nunca crea DeliveryNote/DeliveryNoteLine nuevos ni
recalcula ninguna asignación de máquina/almacén.

Formato del fichero de mapeo (una línea por foto, separador '|'):

    PK|NOMBRE_DE_ARCHIVO

El nombre de archivo es relativo a --dir. Líneas vacías o que
empiecen por '#' se ignoran.

Reutiliza spare_parts.tasks.upload_delivery_note_photo_to_drive
(.run(), ejecución síncrona sin pasar por el broker de Celery) para
la subida a Drive + borrado del archivo local -- misma lógica ya
probada en producción por el flujo normal de confirmación, sin
duplicar código.

Guarda de seguridad: rechaza cualquier DeliveryNote que YA tenga
image, pdf_file o drive_file_id (nunca sobrescribe un archivo
existente). Dry-run por defecto (--apply para ejecutar de verdad),
mismo patrón que delete_all_spare_parts_data.

---

Attaches a historical photo/PDF to an already-existing DeliveryNote
in the DB that ended up without an associated file ("orphaned of
photo") -- real S015 case: 7-8 delivery notes processed by email
while deciding between M365/Google Drive for file persistence,
before spare_parts.gdrive_service existed. Their data is already
extracted and confirmed (status=ASSIGNED) -- this command ONLY
attaches the file, it never creates new DeliveryNote/DeliveryNoteLine
rows nor recalculates any machine/warehouse assignment.

Mapping file format (one line per photo, '|' separator):

    PK|FILENAME

The filename is relative to --dir. Empty lines or lines starting with
'#' are ignored.

Reuses spare_parts.tasks.upload_delivery_note_photo_to_drive
(.run(), synchronous execution bypassing the Celery broker) for the
Drive upload + local file cleanup -- same logic already proven in
production by the normal confirmation flow, no code duplication.

Safety guard: rejects any DeliveryNote that ALREADY has image,
pdf_file or drive_file_id set (never overwrites an existing file).
Dry-run by default (--apply to actually execute), same pattern as
delete_all_spare_parts_data.
"""
import os

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
_PDF_EXTENSIONS = {'.pdf'}


class Command(BaseCommand):
    help = (
        "Adjunta fotos/PDF historicos a DeliveryNote ya existentes "
        "(huerfanos de foto) y los sube a Google Drive. Dry-run por "
        "defecto -- usar --apply para ejecutar de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--map', required=True, dest='map_file',
            help="Ruta al fichero de mapeo PK|NOMBRE_DE_ARCHIVO (una linea por foto).",
        )
        parser.add_argument(
            '--dir', required=True, dest='source_dir',
            help="Directorio donde estan las fotos, referenciadas por --map.",
        )
        parser.add_argument(
            '--apply', action='store_true', default=False,
            help="Ejecuta la asignacion + subida a Drive de verdad. Sin este flag, solo informa.",
        )

    def handle(self, *args, **options):
        from spare_parts.models import DeliveryNote
        from spare_parts.tasks import upload_delivery_note_photo_to_drive

        map_file = options['map_file']
        source_dir = options['source_dir']
        apply_mode = options['apply']

        if not os.path.isfile(map_file):
            raise CommandError(f"Fichero de mapeo no encontrado: {map_file}")
        if not os.path.isdir(source_dir):
            raise CommandError(f"Directorio no encontrado: {source_dir}")

        self.stdout.write(f"# Modo: {'APLICAR' if apply_mode else 'DRY RUN'}")

        entries = []
        with open(map_file, 'r', encoding='utf-8') as f:
            for line_number, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|', 1)
                if len(parts) != 2 or not parts[0].strip().isdigit():
                    raise CommandError(
                        f"Linea {line_number} del mapeo mal formada "
                        f"(esperado 'PK|NOMBRE_DE_ARCHIVO'): {line!r}"
                    )
                entries.append((int(parts[0].strip()), parts[1].strip()))

        if not entries:
            self.stdout.write(self.style.WARNING("# Fichero de mapeo vacio -- nada que hacer."))
            return

        self.stdout.write(f"# {len(entries)} entrada(s) en el mapeo.")

        ok_count = 0
        skip_count = 0
        error_count = 0

        for pk, filename in entries:
            file_path = os.path.join(source_dir, filename)
            prefix = f"# pk={pk} ({filename})"

            try:
                delivery_note = DeliveryNote.objects.get(pk=pk)
            except DeliveryNote.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"{prefix}: DeliveryNote no existe. Omitido."))
                error_count += 1
                continue

            if delivery_note.image or delivery_note.pdf_file or delivery_note.drive_file_id:
                self.stdout.write(self.style.WARNING(
                    f"{prefix}: ya tiene archivo o drive_file_id asignado -- "
                    f"NUNCA se sobrescribe. Omitido."
                ))
                skip_count += 1
                continue

            if not os.path.isfile(file_path):
                self.stdout.write(self.style.ERROR(f"{prefix}: archivo no encontrado en {file_path}. Omitido."))
                error_count += 1
                continue

            extension = os.path.splitext(filename)[1].lower()
            if extension in _IMAGE_EXTENSIONS:
                field_name = 'image'
            elif extension in _PDF_EXTENSIONS:
                field_name = 'pdf_file'
            else:
                self.stdout.write(self.style.ERROR(
                    f"{prefix}: extension no soportada ({extension}). "
                    f"Validas: {sorted(_IMAGE_EXTENSIONS | _PDF_EXTENSIONS)}. Omitido."
                ))
                error_count += 1
                continue

            self.stdout.write(
                f"{prefix}: albaran={delivery_note.delivery_number or 's/n'}, "
                f"proveedor={delivery_note.supplier_name or '?'} -> campo {field_name}"
            )

            if not apply_mode:
                ok_count += 1
                continue

            with open(file_path, 'rb') as fh:
                getattr(delivery_note, field_name).save(
                    filename, File(fh), save=True,
                )

            try:
                upload_delivery_note_photo_to_drive.run(delivery_note.pk)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f"{prefix}: archivo local guardado pero la subida a Drive "
                    f"fallo -- {exc}. Revisar manualmente (el archivo local "
                    f"NO se borra si Drive falla, mismo criterio de siempre)."
                ))
                error_count += 1
                continue

            delivery_note.refresh_from_db()
            if delivery_note.drive_file_id:
                self.stdout.write(self.style.SUCCESS(
                    f"{prefix}: subido a Drive (file_id={delivery_note.drive_file_id})."
                ))
                ok_count += 1
            else:
                self.stdout.write(self.style.WARNING(
                    f"{prefix}: archivo local guardado, pero drive_file_id sigue "
                    f"vacio -- revisar logs (Drive no configurado, o fallo "
                    f"silencioso)."
                ))
                error_count += 1

        self.stdout.write(
            f"# Resumen: {ok_count} OK, {skip_count} omitido(s) (ya tenian "
            f"archivo), {error_count} error(es)."
        )
        if not apply_mode:
            self.stdout.write(self.style.WARNING(
                "# DRY RUN -- nada se ha tocado. Vuelve a ejecutar con "
                "--apply para asignar y subir a Drive de verdad."
            ))
