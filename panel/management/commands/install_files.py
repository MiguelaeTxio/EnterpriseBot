# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/management/commands/install_files.py
"""
Management command: install_files

Reads a multi-file PUT bundle and installs each file to its declared
destination path on the server. The bundle format is:

    # DEST: /absolute/path/to/file.py
    # SEP: <<<EOF_FILE_PY>>>
    [full file content]
    <<<EOF_FILE_PY>>>
    # DEST: /absolute/path/to/other.html
    # SEP: <<<EOF_OTHER_HTML>>>
    [full file content]
    <<<EOF_OTHER_HTML>>>

Rules:
  - DEST line declares the absolute destination path.
  - SEP line declares the closing marker for that file's content block.
  - Content starts on the line immediately after the SEP line.
  - Content ends on the line containing only the closing marker.
  - Intermediate directories are created automatically (exist_ok=True).
  - All files are written with UTF-8 encoding.
  - A summary line is printed for each file: OK or ERROR.
  - Final line: '--- N archivo(s) instalado(s) ---'

Usage:
    python manage.py install_files /home/MiguelAeTxio/SWAP/EnterpriseBot_NNN_PUT.txt
---
Comando de gestión: install_files

Lee un bundle PUT multi-archivo e instala cada archivo en su ruta de
destino declarada en el servidor. El formato del bundle es:

    # DEST: /ruta/absoluta/al/archivo.py
    # SEP: <<<EOF_ARCHIVO_PY>>>
    [contenido completo del archivo]
    <<<EOF_ARCHIVO_PY>>>
    # DEST: /ruta/absoluta/a/otro.html
    # SEP: <<<EOF_OTRO_HTML>>>
    [contenido completo del archivo]
    <<<EOF_OTRO_HTML>>>

Reglas:
  - La línea DEST declara la ruta absoluta de destino.
  - La línea SEP declara el marcador de cierre del bloque de contenido.
  - El contenido empieza en la línea inmediatamente posterior a SEP.
  - El contenido termina en la línea que contiene únicamente el marcador.
  - Los directorios intermedios se crean automáticamente (exist_ok=True).
  - Todos los archivos se escriben con codificación UTF-8.
  - Se imprime una línea de resumen por archivo: OK o ERROR.
  - Línea final: '--- N archivo(s) instalado(s) ---'

Uso:
    python manage.py install_files /home/MiguelAeTxio/SWAP/EnterpriseBot_NNN_PUT.txt
"""

import os

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Installs a multi-file PUT bundle onto the server. "
        "Each file block is declared with # DEST: and # SEP: headers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "bundle_path",
            type=str,
            help="Absolute path to the PUT bundle file on the server.",
        )

    def handle(self, *args, **options):
        bundle_path = options["bundle_path"]

        if not os.path.isfile(bundle_path):
            raise CommandError(
                f"Bundle file not found: {bundle_path}"
            )

        try:
            with open(bundle_path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except Exception as exc:
            raise CommandError(f"Cannot read bundle: {exc}")

        installed = 0
        errors    = 0
        i         = 0
        total     = len(lines)

        while i < total:
            # Scan for the next DEST header line.
            if not lines[i].startswith("# DEST:"):
                i += 1
                continue

            dest_path = lines[i].split("# DEST:", 1)[1].strip()
            i += 1

            # Expect SEP header immediately after DEST.
            if i >= total or not lines[i].startswith("# SEP:"):
                self.stderr.write(
                    f"ERROR  {dest_path} — SEP header missing after DEST"
                )
                errors += 1
                continue

            sep_marker = lines[i].split("# SEP:", 1)[1].strip()
            i += 1

            # Collect content lines until we hit the closing marker.
            content_lines = []
            found_closing = False
            while i < total:
                stripped = lines[i].rstrip("\n").rstrip("\r")
                if stripped == sep_marker:
                    found_closing = True
                    i += 1
                    break
                content_lines.append(lines[i])
                i += 1

            if not found_closing:
                self.stderr.write(
                    f"ERROR  {dest_path} — closing marker '{sep_marker}' not found"
                )
                errors += 1
                continue

            # Write the file.
            try:
                dest_dir = os.path.dirname(dest_path)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                with open(dest_path, "w", encoding="utf-8") as out:
                    out.writelines(content_lines)
                self.stdout.write(f"OK   {dest_path}")
                installed += 1
            except Exception as exc:
                self.stderr.write(f"ERROR  {dest_path} — {exc}")
                errors += 1

        # Final summary.
        self.stdout.write(
            f"--- {installed} archivo(s) instalado(s)"
            + (f", {errors} error(es)" if errors else "")
            + " ---"
        )
