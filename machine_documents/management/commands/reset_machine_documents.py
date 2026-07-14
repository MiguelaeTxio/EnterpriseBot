# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/management/commands/reset_machine_documents.py
"""
Django management command: reset_machine_documents.

Destructive command requested by Miguel Ángel after the 2026-07-14
incident (manual de uso timeout): deletes every MachineDocument row
for a given machine, its local staging file, AND its Drive subfolder
(with everything inside it), to go back to a clean "zona cero" before
repeating the end-to-end panel test.

Requires --confirm -- refuses to run otherwise. --dry-run shows what
would be deleted without touching BD or Drive.

Usage:
    python -m dotenv run python manage.py reset_machine_documents \\
        --machine-code A45 --confirm

---

Comando de gestión Django: reset_machine_documents.

Comando destructivo solicitado por Miguel Ángel tras el incidente del
2026-07-14 (timeout del manual de uso): borra cada fila
MachineDocument de una máquina dada, su archivo local de staging, Y su
subcarpeta de Drive (con todo su contenido), para volver a una "zona
cero" limpia antes de repetir la prueba end-to-end desde el panel.

Requiere --confirm -- se niega a ejecutar si no se pasa. --dry-run
muestra qué se borraría sin tocar BD ni Drive.

Uso:
    python -m dotenv run python manage.py reset_machine_documents \\
        --machine-code A45 --confirm
"""
from django.core.management.base import BaseCommand, CommandError

from fleet.models import MachineAsset
from machine_documents.models import MachineDocument
from spare_parts.gdrive_service import (
    MACHINE_DOCUMENTS_ROOT_FOLDER_NAME,
    GDriveNotConfigured,
    ensure_root_folder,
    get_drive_service,
)

_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class Command(BaseCommand):
    """
    Destructive reset command for MachineDocument -- BD + Drive.
    ---
    Comando destructivo de reinicio para MachineDocument -- BD +
    Drive.
    """

    help = (
        "Borra en BD y en Drive todos los MachineDocument de una "
        "máquina (zona cero). Requiere --confirm."
    )

    def add_arguments(self, parser) -> None:
        """
        Defines the command-line arguments accepted by the command.
        ---
        Define los argumentos de línea de comandos aceptados por el
        comando.
        """
        parser.add_argument(
            "--machine-code",
            required=True,
            type=str,
            help="Código exacto de la máquina (MachineAsset.code), ej. A45.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Obligatorio -- confirma la operación destructiva.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Muestra qué se borraría, sin tocar BD ni Drive.",
        )

    def handle(self, *args, **options) -> None:
        """
        Entry point. Deletes the machine's Drive subfolder (and its
        contents), then every MachineDocument row and its local file.
        ---
        Punto de entrada. Borra la subcarpeta de Drive de la máquina
        (y su contenido), y después cada fila MachineDocument y su
        archivo local.
        """
        machine_code = options["machine_code"]
        dry_run = options["dry_run"]

        if not dry_run and not options["confirm"]:
            raise CommandError(
                "# Operación destructiva -- vuelve a ejecutar con "
                "--confirm para proceder, o con --dry-run para ver "
                "qué se borraría sin tocar nada."
            )

        machine = MachineAsset.objects.filter(code=machine_code).first()
        if not machine:
            raise CommandError(
                f"# No existe MachineAsset con code={machine_code!r}."
            )

        documents = MachineDocument.objects.filter(machine_asset=machine)
        count = documents.count()
        self.stdout.write(
            f"# {count} documento(s) encontrados en BD para "
            f"{machine_code}."
        )

        # ------------------------------------------------------------
        # Drive -- delete the machine's subfolder, which recursively
        # removes every file inside it (same folder
        # _ensure_machine_folder() in gdrive_service.py would find/
        # reuse on the next upload).
        # Drive -- borrar la subcarpeta de la máquina, que elimina
        # recursivamente todos los archivos que contiene (la misma
        # carpeta que _ensure_machine_folder() en gdrive_service.py
        # encontraría/reutilizaría en la siguiente subida).
        # ------------------------------------------------------------
        try:
            drive_service = get_drive_service()
            root_folder_id = ensure_root_folder(
                drive_service,
                folder_name=MACHINE_DOCUMENTS_ROOT_FOLDER_NAME,
            )
            query = (
                f"name='{machine_code}' and "
                f"mimeType='{_FOLDER_MIME_TYPE}' and "
                f"'{root_folder_id}' in parents and trashed=false"
            )
            results = drive_service.files().list(
                q=query, spaces="drive", fields="files(id, name)",
            ).execute()
            matches = results.get("files", [])

            if not matches:
                self.stdout.write(
                    "# No se encontró carpeta Drive para esta "
                    "máquina -- nada que borrar ahí."
                )
            for folder in matches:
                if dry_run:
                    self.stdout.write(
                        f"# [dry-run] Se borraría la carpeta Drive "
                        f"'{folder['name']}' (id={folder['id']})."
                    )
                    continue
                drive_service.files().delete(
                    fileId=folder["id"],
                ).execute()
                self.stdout.write(
                    f"# Carpeta Drive '{folder['name']}' "
                    f"(id={folder['id']}) eliminada."
                )
        except GDriveNotConfigured as exc:
            self.stdout.write(
                f"# Drive no configurado, se omite el borrado en "
                f"Drive: {exc}"
            )

        # ------------------------------------------------------------
        # BD + local staging files.
        # BD + archivos locales de staging.
        # ------------------------------------------------------------
        for document in documents:
            if dry_run:
                self.stdout.write(
                    f"# [dry-run] Se borraría MachineDocument "
                    f"#{document.pk} ({document.display_name}) y su "
                    f"archivo local."
                )
                continue
            if document.source_file:
                document.source_file.delete(save=False)
            document.delete()

        if dry_run:
            self.stdout.write(
                "# [dry-run] Fin -- no se ha borrado nada realmente."
            )
        else:
            self.stdout.write(
                f"# {count} documento(s) eliminados de BD, archivos "
                f"locales borrados y carpeta Drive eliminada. Zona "
                f"cero lista para {machine_code}."
            )
