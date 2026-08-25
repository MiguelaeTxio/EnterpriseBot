# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/cerrar_retenciones_y_manuales.py
"""
H30 (S68) -- Punto 3 de la hoja de ruta, parte cerrable hoy sin
diseño pendiente:

- `RETENCIONES` (14 archivos, `DOC. PERSONAL/RETENCIONES/<año>/`):
  certificados de retenciones por EMPRESA (Grúas Adolfo Álvarez,
  Transgrual, Benajarafe XXI...), no por persona. Miguel Ángel,
  verbatim: "se crea un tipo para guardar por empresa" -- sin split
  por persona, aunque ya existan 4 extractos manuales sueltos
  ("Páginas desde...") mezclados en la misma carpeta. Tipo nuevo
  (no existía en el catálogo, verificado en S68): domain=COMPANY,
  family=FINANCIERO.

- `MANUAL_USO`/`MANUAL_DESPIECE` -- AMBOS YA EXISTÍAN en el catálogo
  desde antes de H30 (verificado en S68, nunca se habían aplicado a
  estos archivos concretos). Confirmado contra
  `ENTERPRISEBOT_ATTACHED_MILESTONE_V29.md`: "MANUALES DE USO" es el
  nombre actual de la antigua jerarquía "MANUAL DE INSTRUCCIONES/
  {CODIGO}/...". Se aplica a:
    * `DOC. MAQUINAS/MANUAL DE INSTRUCCIONES/<código>/` (10 archivos)
      -> MANUAL_USO completo.
    * Góndola G-17 Scheuerle, solo las dos subcarpetas confirmadas a
      mano por Miguel Ángel: "01 Operation Instructions" -> MANUAL_USO,
      "05 Spare Parts" -> MANUAL_DESPIECE. El resto del manual del
      fabricante (02 Certificate, 04 Loading diagrams, 06 Manufacturers
      documentation, 07 Circuit diagrams -- 17 archivos) NO se toca
      aquí, no encaja en el reparto acordado y no se fuerza.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog

RETENCIONES_ROOT = "DOC. PERSONAL/RETENCIONES/"
MANUAL_INSTRUCCIONES_ROOT = "DOC. MAQUINAS/MANUAL DE INSTRUCCIONES/"
SCHEUERLE_ROOT = (
    "DOC. MAQUINAS/REMOLQUES Y GONDOLAS (R y G)/GONDOLAS/G-17 SCHEUERLE/"
    "MANUAL OPERACIONES FABRICANTE ALEMAN/"
)
SCHEUERLE_SUBCARPETAS = {
    "01 Operation Instructions": "MANUAL_USO",
    "05 Spare Parts": "MANUAL_DESPIECE",
}


class Command(BaseCommand):
    help = (
        "H30 (S68) Punto 3 -- crea RETENCIONES y clasifica RETENCIONES/"
        "MANUAL_USO/MANUAL_DESPIECE. Dry-run por defecto, --apply para "
        "escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        if not DocumentTypeCatalog.objects.filter(code="RETENCIONES").exists():
            if apply_changes:
                DocumentTypeCatalog.objects.create(
                    code="RETENCIONES",
                    label="Certificado de retenciones (por empresa)",
                    domain=DocumentTypeCatalog.DOMAIN_COMPANY,
                    family=DocumentTypeCatalog.FAMILY_FINANCIERO,
                )
                self.stdout.write("TIPO CREADO: RETENCIONES")
            else:
                self.stdout.write("CREARIA TIPO: RETENCIONES (COMPANY / FINANCIERO)")
        else:
            self.stdout.write("YA EXISTE, no se toca: RETENCIONES")

        pks_por_tipo = {}

        for entry in DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez", entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            parent_path__startswith=RETENCIONES_ROOT,
            document_type__isnull=True,
        ).only("id", "parent_path", "name").iterator():
            pks_por_tipo.setdefault("RETENCIONES", []).append(entry.pk)
            self.stdout.write("CLASIFICAR (RETENCIONES): %s / %s" % (entry.parent_path, entry.name))

        for entry in DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez", entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            parent_path__startswith=MANUAL_INSTRUCCIONES_ROOT,
            document_type__isnull=True,
        ).only("id", "parent_path", "name").iterator():
            pks_por_tipo.setdefault("MANUAL_USO", []).append(entry.pk)
            self.stdout.write("CLASIFICAR (MANUAL DE INSTRUCCIONES -> MANUAL_USO): %s / %s" % (entry.parent_path, entry.name))

        for subcarpeta, code in SCHEUERLE_SUBCARPETAS.items():
            prefijo = SCHEUERLE_ROOT + subcarpeta + "/"
            for entry in DocumentIndexEntry.objects.filter(
                bucket="cgs_grupo_alvarez", entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
                parent_path__startswith=prefijo,
                document_type__isnull=True,
            ).only("id", "parent_path", "name").iterator():
                pks_por_tipo.setdefault(code, []).append(entry.pk)
                self.stdout.write("CLASIFICAR (Scheuerle %s -> %s): %s / %s" % (subcarpeta, code, entry.parent_path, entry.name))

        totales = {}
        for code, pks in pks_por_tipo.items():
            totales[code] = len(pks)
            if apply_changes:
                tipo = DocumentTypeCatalog.objects.get(code=code)
                n = DocumentIndexEntry.objects.filter(pk__in=pks).update(document_type=tipo)
                self.stdout.write("APLICADO %s: %d archivos" % (code, n))

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for code, n in totales.items():
            self.stdout.write("    %s: %d archivos" % (code, n))
