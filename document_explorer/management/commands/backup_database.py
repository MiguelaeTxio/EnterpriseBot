# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/backup_database.py
"""
Take one database copy now (H24, S146), outside the 3:00 schedule.

---

Hace una copia de la base de datos en el momento, igual que la tarea
diaria de las 3:00 (`backup_database_task`): volcado por tubería al
cubo, sin pasar por el disco del servidor. El agente H28 la baja a
OneDrive en su siguiente consulta (cada 10 minutos).

`--log-file` obligatorio: log propio en pantalla y en archivo a la vez.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from document_explorer.db_backup_service import run_backup


class Command(BaseCommand):
    """
    Take one database copy now.

    ---

    Hace una copia de la base de datos en el momento.
    """

    help = "Hace una copia de la base de datos ahora (H24, S146)."

    def add_arguments(self, parser):
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one timestamped line to the log, flushed.

        ---

        Escribe una línea con hora en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def _log_plain(self, message):
        """
        Same as _log, without the time (final summary).

        ---

        Igual que _log, sin hora (resumen final).
        """
        print(message, flush=True)
        self._handle.write(message + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._log("Volcando la base de datos al cubo...")
            backup = run_backup()
            self._log("Terminado.")
            self._log_plain("RESUMEN")
            self._log_plain("Archivo: %s" % backup.file_name)
            self._log_plain("Estado: %s" % backup.get_status_display())
            self._log_plain("Comprimido: %d bytes" % backup.size_bytes)
            self._log_plain(
                "Sin comprimir: %d bytes" % backup.uncompressed_bytes)
            self._log_plain("SHA-256: %s" % backup.sha256)
            for moment, counts in (backup.row_counts or {}).items():
                for table, rows in counts.items():
                    self._log_plain("Filas %s %s: %s" % (
                        moment, table, rows))
            if backup.error:
                self._log_plain("Error: %s" % backup.error)
