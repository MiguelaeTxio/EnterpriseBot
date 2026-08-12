# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_obsoleto_folder_flag.py
"""
H30 (S50) -- corrige el desfase real detectado al revisar los
empates de resolve_vigencia: archivos que ya viven dentro de una
carpeta llamada literalmente OBSOLETO/OBSOLETOS en el arbol virtual,
pero cuyo campo is_obsolete sigue en False. La organizacion manual
por carpeta nunca se ha reflejado en el campo real.

Dos patrones reales, confirmados con datos reales en S50 (3.835
archivos totales bajo alguna carpeta "obsolet*"):

- CASO A (seguro, se marca): "obsoleto" aparece como subcarpeta
  DENTRO del arbol propio de una maquina concreta ya identificada --
  ej. ".../A-59  E-5068-BHH/OBSOLETO", ".../P-07 2728-BJB.../P-07/
  OBSOLETOS". Mismo patron ya confirmado al fusionar pk 607 (S50):
  documentos viejos de ESA maquina, superados por otros mas
  recientes. Deteccion: el segmento inmediatamente despues de la
  familia (indice 2 del path completo, "DOC. MAQUINAS/<FAMILIA>/
  <segmento>/...") es un identificador de maquina real, no la
  palabra "obsoleto" en si.

- CASO B (nunca se toca aqui): "OBSOLETO" es el propio segmento de
  familia -- una carpeta de primer nivel que archiva maquinas
  ENTERAS dadas de baja (ej. "CABEZAS TRACTORAS (P)/OBSOLETO/
  OBSOLETO P07"). Aqui is_obsolete de documento no es el concepto
  correcto -- es baja de maquina (DOC_BAJA_DEFINITIVA), un campo
  distinto. Detectado por el mismo indice 2 siendo literalmente
  "obsoleto".

DRY-RUN POR DEFECTO. Con --apply escribe is_obsolete=True de verdad
solo en el caso A -- nunca toca el caso B, nunca borra filas, nunca
toca GCS (4.12).
"""
from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry


class Command(BaseCommand):
    help = (
        "H30 (S50) -- marca is_obsolete=True para archivos ya "
        "organizados manualmente en una subcarpeta OBSOLETO/OBSOLETOS "
        "dentro del arbol de una maquina concreta (caso A). Nunca "
        "toca las carpetas OBSOLETO de familia completa (caso B, "
        "maquinas de baja). Dry-run por defecto, usar --apply."
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
            deleted_at__isnull=True,
            purged_at__isnull=True,
        ).filter(parent_path__iregex=r"obsolet")

        stats = {"caso_a_marcado": 0, "caso_b_excluido": 0}
        caso_b_carpetas = set()
        marcados_muestra = []

        for entry in base.iterator():
            segmentos = [s for s in entry.parent_path.split("/") if s]
            familia_pos = segmentos[2] if len(segmentos) > 2 else None
            es_caso_b = bool(familia_pos) and "obsolet" in familia_pos.lower()

            if es_caso_b:
                stats["caso_b_excluido"] += 1
                caso_b_carpetas.add(entry.parent_path)
                continue

            stats["caso_a_marcado"] += 1
            if len(marcados_muestra) < 50:
                marcados_muestra.append((entry.pk, entry.name, entry.parent_path))
            if apply_changes:
                entry.is_obsolete = True
                entry.save(update_fields=["is_obsolete"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
        self.stdout.write("    muestra caso A (marcado, hasta 50):")
        for pk, name, path in marcados_muestra:
            self.stdout.write("        pk=%d  %s  [%s]" % (pk, name, path))
        self.stdout.write("    carpetas caso B excluidas (nunca tocadas, hasta 30):")
        for folder in sorted(caso_b_carpetas)[:30]:
            self.stdout.write("        %s" % folder)
