# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_variant_marker_duplicates.py
"""
H30 (S50) -- resuelve empates de fecha entre dos DocumentIndexEntry
del mismo tipo y sujeto cuando el propio nombre de archivo lleva un
marcador tecnico inequivoco de cual es la copia "buena":

- "_unlocked": el PDF original vino con proteccion de contrasena y
  alguien genero una version sin ella -- la version _unlocked es la
  realmente utilizable (se puede abrir sin pedir contrasena), se
  queda vigente. La version bloqueada (sin el sufijo) pasa a
  obsoleta.
- "- copia" / "-copia" / "copia" como palabra suelta: literalmente
  marcada como copia por quien la subio -- la version SIN esa
  palabra se queda vigente, la copia pasa a obsoleta.

Alcance deliberadamente estrecho, igual criterio que
resolve_itv_ficha_tecnica_dossier -- solo grupos de exactamente 2
entradas, mismo sujeto y tipo, misma fecha efectiva, y exactamente
una de las dos con el marcador (nunca las dos, nunca ninguna). Casos
reales fuera de este patron (p.ej. "CERTIFICADO OCA" vs "REV OCA", o
dos variantes ya "_unlocked" ambas sin marcador que las diferencie)
quedan fuera a proposito, listados en el informe para revision
manual -- nunca se adivina.

DRY-RUN POR DEFECTO. Con --apply escribe is_obsolete=True de verdad
en el perdedor. Nunca borra filas, nunca toca GCS (4.12).
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry

MARKERS = ("_UNLOCKED", " COPIA", "-COPIA")


class Command(BaseCommand):
    help = (
        "H30 (S50) -- resuelve empates de fecha con marcador tecnico "
        "de duplicado en el nombre (_unlocked / copia). Dry-run por "
        "defecto, usar --apply."
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
            fecha_a = a.expiry_date or a.issue_date
            fecha_b = b.expiry_date or b.issue_date
            if fecha_a != fecha_b:
                continue

            name_a, name_b = a.name.upper(), b.name.upper()

            unlocked_a = "_UNLOCKED" in name_a
            unlocked_b = "_UNLOCKED" in name_b
            if unlocked_a != unlocked_b:
                ganador, perdedor = (a, b) if unlocked_a else (b, a)
                stats["resueltos_unlocked"] += 1
                motivo = "_unlocked prevalece sobre version bloqueada"
            else:
                copia_a = "COPIA" in name_a
                copia_b = "COPIA" in name_b
                if copia_a != copia_b:
                    ganador, perdedor = (b, a) if copia_a else (a, b)
                    stats["resueltos_copia"] += 1
                    motivo = "version sin 'copia' prevalece"
                else:
                    stats["fuera_de_alcance"] += 1
                    fuera_de_alcance_detalle.append(
                        (key[1], key[2], [(e.pk, e.name) for e in entries])
                    )
                    continue

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
        self.stdout.write("    fuera de alcance, sin marcador claro:")
        for obj_id, type_id, detalle in fuera_de_alcance_detalle:
            self.stdout.write("        sujeto=%s tipo=%s %s" % (obj_id, type_id, detalle))
