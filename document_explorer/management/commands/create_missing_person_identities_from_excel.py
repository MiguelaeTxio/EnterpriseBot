# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/create_missing_person_identities_from_excel.py
"""
H30 (S66). Corrige un fallo real de diseno detectado esta sesion:
`import_worker_machine_excel.py` ya detectaba DNIs del Excel sin
`PersonIdentity` correspondiente (`workers_unmatched`), pero nunca los
creaba -- solo actualizaba metadatos (is_active_employee, fechas de
caducidad...) sobre fichas YA existentes. Un trabajador activo real
segun el Excel, sin ficha, se quedaba sin ficha para siempre.

Decision explicita de Miguel Angel (S66), verbatim: *"la fuente de
verdad de los trabajadores activos es el Excel [...] hay que coger
el primero, ¿tiene ficha? No, se le crea [...] Y luego lo que
encontremos en documentos se le asigna. No al reves."* -- el Excel
manda, nunca el directorio de documentos. Este comando recorre el
Excel (misma deteccion de cabecera/alias que import_worker_machine_
excel.py, reutilizada tal cual para no divergir) y, para cada DNI sin
ficha, intenta localizar su carpeta real dentro de DOC. PERSONAL por
nombre (busqueda de carpetas FOLDER cuyo nombre normalizado coincide
con "APELLIDOS NOMBRE" del Excel, sin coma). Solo crea la ficha
cuando la carpeta resuelve con UNA UNICA coincidencia -- cero o mas
de una coincidencia se reporta para revision manual, nunca se
adivina (mismo criterio que el resto de H30).

DRY-RUN POR DEFECTO. Con --apply escribe de verdad. Nunca borra ni
modifica una PersonIdentity ya existente -- solo crea las que faltan.
"""
import os
import re

from django.core.management.base import BaseCommand
import openpyxl

from document_explorer.management.commands.import_worker_machine_excel import (
    WORKER_SHEETS, WORKER_HEADER_ALIASES, EXCEL_PATH,
    _find_header_row, _map_headers, _norm_dni,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity


def _strip_accents(value):
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_name(raw):
    """"APELLIDO1 APELLIDO2, NOMBRE" o variantes -> clave comparable,
    sin coma, sin acentos, mayusculas, espacios colapsados."""
    text = _strip_accents(raw).upper()
    text = text.replace(",", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_surnames_and_name(raw):
    """
    Parte "APELLIDO1 APELLIDO2, NOMBRE" (formato real del Excel) en
    (first_surname, second_surname, given_name). Si no hay coma, el
    primer token es first_surname y el resto given_name (sin
    second_surname) -- caso real visto en el Excel ("BENALI, RACHID"
    solo trae un apellido).
    """
    raw = raw.strip()
    if "," in raw:
        apellidos, nombre = raw.split(",", 1)
    else:
        parts = raw.split(" ", 1)
        apellidos = parts[0]
        nombre = parts[1] if len(parts) > 1 else ""
    apellidos = apellidos.strip()
    nombre = nombre.strip()
    surname_parts = apellidos.split(" ", 1)
    first_surname = surname_parts[0].strip()
    second_surname = surname_parts[1].strip() if len(surname_parts) > 1 else ""
    return first_surname, second_surname, nombre


def _find_folder_candidates(normalized_name):
    """
    Busca carpetas FOLDER reales dentro de DOC. PERSONAL cuyo nombre
    normalizado (sin acentos/coma, mayusculas) sea EXACTAMENTE igual
    a `normalized_name`, o lo contenga como prefijo (para el caso de
    sufijos reales tipo " (GR)"/" (TR)"). Nunca por parecido difuso.
    """
    candidates = []
    qs = DocumentIndexEntry.objects.filter(
        parent_path__startswith="DOC. PERSONAL",
        entry_kind=DocumentIndexEntry.KIND_FOLDER,
        deleted_at__isnull=True,
    ).only("id", "parent_path", "name")
    for entry in qs:
        folder_norm = _normalize_name(entry.name)
        if folder_norm == normalized_name or folder_norm.startswith(
            normalized_name + " ("
        ):
            candidates.append(entry)
    return candidates


class Command(BaseCommand):
    help = (
        "H30 (S66) -- crea las PersonIdentity que faltan usando el "
        "Excel como fuente de verdad de trabajadores activos. "
        "Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--excel-path", default=EXCEL_PATH,
            help="Ruta alternativa al .xlsx, si no es la version commiteada.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        excel_path = options["excel_path"]

        if not os.path.isfile(excel_path):
            self.stderr.write("No se encuentra el Excel en: %s" % excel_path)
            return

        wb = openpyxl.load_workbook(excel_path, data_only=True)

        seen_dni = set()
        ya_existe = 0
        creadas = []
        pendientes_revision = []

        for sheet_name in WORKER_SHEETS:
            if sheet_name not in wb.sheetnames:
                self.stdout.write(
                    "AVISO: hoja no encontrada, saltada: %r" % sheet_name
                )
                continue
            ws = wb[sheet_name]
            header_row, raw_headers = _find_header_row(ws, ["DNI", "NOMBRE"])
            if header_row is None:
                self.stdout.write(
                    "AVISO: %s sin cabecera reconocible" % sheet_name
                )
                continue
            columns = _map_headers(raw_headers, WORKER_HEADER_ALIASES)
            if "dni" not in columns or "nombre" not in columns:
                self.stdout.write(
                    "AVISO: %s sin columna DNI/NOMBRE localizada" % sheet_name
                )
                continue

            for r in range(header_row + 1, ws.max_row + 1):
                raw_dni = ws.cell(row=r, column=columns["dni"]).value
                dni = _norm_dni(raw_dni)
                if not dni:
                    continue
                if dni in seen_dni:
                    continue
                seen_dni.add(dni)

                raw_nombre = ws.cell(row=r, column=columns["nombre"]).value
                if not raw_nombre:
                    self.stdout.write(
                        "%s fila %d: DNI %s sin NOMBRE TRABAJADOR -- "
                        "revision manual" % (sheet_name, r, dni)
                    )
                    pendientes_revision.append((dni, None, "sin nombre en Excel"))
                    continue
                nombre_raw = str(raw_nombre).strip()

                if PersonIdentity.objects.filter(dni=dni).exists():
                    ya_existe += 1
                    continue

                normalized = _normalize_name(nombre_raw)
                candidates = _find_folder_candidates(normalized)

                if len(candidates) != 1:
                    motivo = (
                        "sin carpeta encontrada" if not candidates
                        else "%d carpetas candidatas ambiguas" % len(candidates)
                    )
                    self.stdout.write(
                        "%s fila %d: DNI %s (%s) -- %s, NO se crea, "
                        "revision manual" % (
                            sheet_name, r, dni, nombre_raw, motivo,
                        )
                    )
                    for c in candidates:
                        self.stdout.write("    candidata: %s" % c.parent_path + "/" + c.name)
                    pendientes_revision.append((dni, nombre_raw, motivo))
                    continue

                folder_entry = candidates[0]
                folder_path = "%s/%s" % (
                    folder_entry.parent_path, folder_entry.name,
                )
                first_surname, second_surname, given_name = (
                    _split_surnames_and_name(nombre_raw)
                )
                self.stdout.write(
                    "%s fila %d: DNI %s (%s) -> CREAR ficha, carpeta: %s"
                    % (sheet_name, r, dni, nombre_raw, folder_path)
                )
                creadas.append({
                    "dni": dni, "first_surname": first_surname,
                    "second_surname": second_surname,
                    "given_name": given_name, "folder_path": folder_path,
                })

        self.stdout.write("")
        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self.stdout.write("Ya tenian ficha: %d" % ya_existe)
        self.stdout.write("Fichas nuevas a crear: %d" % len(creadas))
        self.stdout.write(
            "Pendientes de revision manual (sin carpeta clara): %d"
            % len(pendientes_revision)
        )

        if apply_changes:
            for c in creadas:
                PersonIdentity.objects.create(
                    dni=c["dni"],
                    first_surname=c["first_surname"],
                    second_surname=c["second_surname"],
                    given_name=c["given_name"],
                    folder_path=c["folder_path"],
                    is_active_employee=True,
                )
                self.stdout.write("CREADA: %s" % c["dni"])
