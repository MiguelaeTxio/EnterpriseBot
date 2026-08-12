# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_variant_marker_duplicates.py
"""
H30 (S50) -- resuelve duplicados entre dos DocumentIndexEntry del
mismo tipo y sujeto cuando el propio nombre de archivo lleva un
marcador tecnico inequivoco de cual es la copia "buena":

- "_unlocked" (+ opcional "(1)"/"(2)" de version): el PDF original
  vino con proteccion de contrasena y alguien genero una version sin
  ella -- la version _unlocked es la realmente utilizable (se puede
  abrir sin pedir contrasena), se queda vigente. La bloqueada pasa a
  obsoleta.
- "- copia" / "-copia" / " copia" como palabra suelta: literalmente
  marcada como copia por quien la subio -- la version SIN esa
  palabra se queda vigente, la copia pasa a obsoleta.

CORREGIDO EN LA MISMA SESION (S50): la primera version comparaba
`expiry_date or issue_date` entre los dos miembros y solo actuaba si
coincidian -- pero como la inmensa mayoria de estas filas no tienen
fecha extraida todavia, `None == None` colaba como "misma fecha" y
emparejaba documentos que NO son el mismo archivo (ej. sujeto=271:
"B-33 REC SEG GENERALI 31-12-2025.pdf" vs "REC POL C6A960000357 ASADA
31-12-25_unlocked.pdf" -- aseguradoras distintas, dos recibos reales
distintos, ninguno de los dos con fecha real, coincidian solo por el
bug). Corregido exigiendo que el nombre, tras quitar UNICAMENTE el
marcador tecnico y normalizar espacios/mayusculas, sea EXACTAMENTE
igual al del otro miembro -- la fecha ya no interviene en absoluto en
esta decision, el nombre normalizado es la unica prueba valida de que
es el mismo documento.

Alcance deliberadamente estrecho -- solo grupos de exactamente 2
entradas, mismo sujeto y tipo, y el nombre base normalizado
IDENTICO entre ambas tras quitar el marcador. Casos reales fuera de
este patron (nombres distintos de verdad, aunque compartan tipo y
sujeto) quedan fuera a proposito, listados para revision manual --
nunca se adivina.

DRY-RUN POR DEFECTO. Con --apply escribe is_obsolete=True de verdad
en el perdedor. Nunca borra filas, nunca toca GCS (4.12).
"""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry

_UNLOCKED_RE = re.compile(r"_UNLOCKED(\s*\(\d+\))?", re.IGNORECASE)
_COPIA_RE = re.compile(r"\s*-?\s*COPIA\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(name):
    stem, dot, ext = name.upper().rpartition(".")
    stem = stem if dot else name.upper()
    stem = _UNLOCKED_RE.sub("", stem)
    stem = _COPIA_RE.sub("", stem)
    stem = _WHITESPACE_RE.sub(" ", stem).strip()
    return stem


class Command(BaseCommand):
    help = (
        "H30 (S50) -- resuelve duplicados con marcador tecnico en el "
        "nombre (_unlocked / copia) cuando el nombre base, sin el "
        "marcador, es identico entre los dos. Dry-run por defecto, "
        "usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe is_obsolete=True de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        base = DocumentIndexEntry.objects.filter(
            entry_kind=DocumentIndexEntry.KIND_FILE,
            is_obsolete=False,
            document_type__isnull=False,
            domain_object_id__isnull=False,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        ).select_related("document_type")

        groups = defaultdict(list)
        for e in base:
            groups[(e.domain_content_type_id, e.domain_object_id, e.document_type_id)].append(e)

        stats = {"resueltos_unlocked": 0, "resueltos_copia": 0, "fuera_de_alcance": 0}
        fuera_de_alcance_detalle = []

        for key, entries in groups.items():
            if len(entries) != 2:
                continue

            a, b = entries
            name_a, name_b = a.name.upper(), b.name.upper()

            unlocked_a = bool(_UNLOCKED_RE.search(name_a))
            unlocked_b = bool(_UNLOCKED_RE.search(name_b))
            copia_a = bool(_COPIA_RE.search(name_a))
            copia_b = bool(_COPIA_RE.search(name_b))

            tiene_marcador = (unlocked_a != unlocked_b) or (copia_a != copia_b)
            if not tiene_marcador:
                continue

            if _normalize(a.name) != _normalize(b.name):
                # Mismo tipo/sujeto, uno de los dos con marcador, pero
                # el nombre base NO coincide de verdad -- no es el
                # mismo documento, es una coincidencia. Nunca se toca.
                stats["fuera_de_alcance"] += 1
                fuera_de_alcance_detalle.append(
                    (key[1], key[2], [(e.pk, e.name) for e in entries])
                )
                continue

            if unlocked_a != unlocked_b:
                ganador, perdedor = (a, b) if unlocked_a else (b, a)
                stats["resueltos_unlocked"] += 1
                motivo = "_unlocked prevalece sobre version bloqueada (mismo nombre base)"
            else:
                ganador, perdedor = (b, a) if copia_a else (a, b)
                stats["resueltos_copia"] += 1
                motivo = "version sin 'copia' prevalece (mismo nombre base)"

            self.stdout.write(
                "%s  sujeto=%s tipo=%s | perdedor pk=%d (%s) -> obsoleto=True | "
                "vigente pk=%d (%s) | %s"
                % (
                    "APLICADO" if apply_changes else "CANDIDATO",
                    key[1], key[2], perdedor.pk, perdedor.name,
                    ganador.pk, ganador.name, motivo,
                )
            )
            if apply_changes:
                perdedor.is_obsolete = True
                perdedor.save(update_fields=["is_obsolete"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for k, v in stats.items():
            self.stdout.write("    %s: %d" % (k, v))
        self.stdout.write("    fuera de alcance (marcador presente pero nombre base distinto):")
        for obj_id, type_id, detalle in fuera_de_alcance_detalle:
            self.stdout.write("        sujeto=%s tipo=%s %s" % (obj_id, type_id, detalle))
