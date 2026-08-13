# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase_b0_filename_dates.py
"""
H30 (S48) -- Fase B0: extracción de fecha por heurística de NOMBRE de
archivo, para los tipos `tracks_expiry=True` que ya tienen
`document_type`/`domain_object` resueltos por la Fase A pero todavía
sin `expiry_date`/`issue_date`. Precede siempre al OCR (Fase B1) --
gratis, sin abrir el documento, mismo principio de coste que el resto
del hito.

Criterios confirmados por Miguel Ángel con datos reales (S48), nunca
generalizados sin evidencia -- ver anexo H30, sección "COMPLETADAS EN
S48":

- `ITV`, `OCA`, `CARNET_CONDUCIR`: fecha unica en el nombre = fecha de
  CADUCIDAD (`expiry_date`). Confirmado con muestras reales donde la
  misma maquina/persona tiene varias fechas futuras a lo largo de los
  años (renovacion periodica).
- `PERMISO_CIRCULACION`, `FORMACION`: fecha unica en el nombre = fecha
  de EMISION (`issue_date`). Confirmado con muestras reales sin
  repeticion de fecha para el mismo sujeto (no hay patron de
  renovacion visible).
- `SEGURO` -- tres subpatrones reales distintos, confirmados tras
  revisar el resultado real de OCR (Fase B1) sobre 100 documentos: la
  inmensa mayoria son avisos bancarios de domiciliacion demasiado
  variados para OCR por contexto, pero el propio nombre ya trae el
  dato en la mayoria de casos (994/1393, 71%):
    1. Fecha unica en el nombre -> `issue_date` (fecha de
       emision/cobro del recibo, nunca caducidad -- el unico caso que
       si funciono por OCR mostro que la fecha del nombre cae un dia
       DESPUES de que termine el periodo cubierto).
    2. Notacion de trimestre ("1º TR. 2013", "2º TR 2014"...) ->
       `issue_date` = primer dia de ese trimestre.
    3. Rango explicito ("X a Y") -> `expiry_date` = fecha Y (fin del
       periodo cubierto).
- `EXCEDENCIA`: sin patron de fecha en el nombre verificado (0/2
  muestras) -- va integramente por OCR (Fase B1), este comando no lo
  toca.
- Cualquier otro tipo `tracks_expiry=True` no listado aqui
  (`TACOGRAFO`, `CONTRATO`, `AUTORIZACION_USO_MAQUINARIA`) tampoco se
  toca -- sin verificar con datos reales todavia.

DRY-RUN POR DEFECTO. Sin `--apply`, solo informa. Con `--apply`,
escribe `expiry_date`/`issue_date` de verdad.
"""
from django.core.management.base import BaseCommand

from document_explorer.filename_date_service import (
    FIELD_BY_CODE, extract_date_by_filename,
)
from document_explorer.models import DocumentIndexEntry

BUCKET = "cgs_grupo_alvarez"


class Command(BaseCommand):
    help = (
        "H30 (S48) -- Fase B0: fecha por heuristica de nombre para "
        "ITV/OCA/CARNET_CONDUCIR/PERMISO_CIRCULACION/FORMACION/"
        "SEGURO. Dry-run por defecto, usar --apply para escribir de "
        "verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        stats = {"con_fecha": 0, "sin_fecha_en_nombre": 0}

        codes = list(FIELD_BY_CODE) + ["SEGURO"]
        qs = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code__in=codes,
            expiry_date__isnull=True, issue_date__isnull=True,
            domain_object_id__isnull=False,
        ).select_related("document_type")

        for entry in qs:
            code = entry.document_type.code
            result = extract_date_by_filename(code, entry.name)
            if not result:
                stats["sin_fecha_en_nombre"] += 1
                continue
            field, found = result

            stats["con_fecha"] += 1
            self.stdout.write(
                "%s -> %s=%s  [%s] %s"
                % (code, field, found.isoformat(),
                   entry.parent_path, entry.name)
            )
            if apply_changes:
                if field == "expiry":
                    entry.expiry_date = found
                    entry.save(update_fields=["expiry_date"])
                else:
                    entry.issue_date = found
                    entry.save(update_fields=["issue_date"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
