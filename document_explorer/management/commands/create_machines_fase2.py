# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/create_machines_fase2.py
"""
H30 (S117) -- FASE 2 DE MÁQUINAS: alta DESDE CONSOLA de las máquinas
que tienen documentación en DOC. MAQUINAS pero no existían en Centros
de gasto, y asignación de los documentos de su carpeta.

Decisión de Miguel Ángel tras el dry-run de Fase 2 (EnterpriseBot_012):
"Las damos de alta, pero desde consola", con la tabla de códigos que
se le propuso y confirmó ("Sigue"): matrícula como código cuando la
hay; si no, nombre corto en mayúsculas (estilo PAOLA, LILI, FURGLAR de
la flota real). Familia VACÍA a propósito -- la elige Yolanda en la
ficha, nunca se inventa la clasificación. Empresa: mismos campos
reales que el alta automática de classification_service (máquina GRA
de referencia), nunca inventados.

Cada máquina se asocia a su(s) carpeta(s) exacta(s) (prefijo de
parent_path). ALTESUR tiene tres plataformas en la MISMA carpeta: cada
una se lleva solo los archivos cuyo nombre contiene su matrícula.

Idempotente: si el código ya existe, se reutiliza (nunca se duplica).
Solo toca documentos vivos SIN máquina (domain_object_id nulo), con o
sin tipo -- los que aún no tienen tipo quedan ya con su máquina para
la Fase 3 (OCR). Nunca toca GCS (4.12).

DRY-RUN por defecto; --apply escribe. Log propio con heartbeat y ETA
(com-standards 0bis/0ter).
"""
import re
import time
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
REFERENCE_COMPANY_CODE = "GRA"
ROOT = "DOC. MAQUINAS/"

MACHINES = [
    {"code": "4980JVX", "plate": "4980JVX", "brand_model": "Plataforma cesta (Altesur)",
     "folders": ["PLATAFORMAS (Z)/ALTESUR"], "name_contains": "4980JVX"},
    {"code": "5032KDS", "plate": "5032KDS", "brand_model": "Plataforma cesta (Altesur)",
     "folders": ["PLATAFORMAS (Z)/ALTESUR"], "name_contains": "5032KDS"},
    {"code": "8834KFJ", "plate": "8834KFJ", "brand_model": "Plataforma cesta (Altesur)",
     "folders": ["PLATAFORMAS (Z)/ALTESUR"], "name_contains": "8834KFJ"},
    {"code": "MA5936", "plate": "MA5936", "brand_model": "Tractor",
     "folders": ["TRACTOR"]},
    {"code": "BARCA", "brand_model": "Embarcación de Alberto Álvarez",
     "folders": [
         "BARCA ALBERTO ALVAREZ",
         "VEHICULOS DE EMPRESA/AA PARTICULAR VEHICULOS/DOCUMENT EMBARCACION ALBERTO",
     ]},
    {"code": "LEANDRO", "brand_model": "Vehículo particular de Leandro Álvarez",
     "folders": ["VEHICULOS DE EMPRESA/AA PARTICULAR VEHICULOS/LEANDRO ALVAREZ"]},
    {"code": "HINOWA251", "brand_model": "Hinowa (n.º serie 251L4ULAX08)",
     "folders": ["MAQUINARIA OTROS/MAMMSA/HINOWA 251L4ULAX08"]},
    {"code": "HINOWA583", "brand_model": "Hinowa (n.º serie 583L9IM08X08)",
     "folders": ["MAQUINARIA OTROS/MAMMSA/HINOWA 583L9IM08X08"]},
    {"code": "JENG", "brand_model": "Minigrúa Jeng",
     "folders": ["GRUAS MOVILES (A)/MINIGRUA/MINIGRUA JENG"]},
    {"code": "GEMETALURG", "brand_model": "Grupo electrógeno (Metalúrgica Andaluza)",
     "folders": ["CERTIFICADOS DE EQUIPOS DE TRABAJO ( UTILLAJE)/DOC.GRUPO ELECTROGENO-METALURGICA ANDALUZA"]},
    {"code": "GENERADOR", "brand_model": "Generador",
     "folders": ["CERTIFICADOS DE EQUIPOS DE TRABAJO ( UTILLAJE)/DOC.GENERADOR"]},
    {"code": "GEPEPE", "brand_model": "Grupo electrógeno (Pepe, asistencia)",
     "folders": ["GRUPO ELECTROGENOS/PEPE ASISTENCIA"]},
    {"code": "COMPMALAGA", "brand_model": "Compresor de plataformas (Málaga)",
     "folders": ["COMPRESORES/MALAGA/COMPRESOR PLATAFORMAS"]},
    {"code": "DEPGASOIL", "brand_model": "Depósito de gasoil",
     "folders": ["DESPOSITOS GASOIL"]},
    {"code": "DEPAGUAMLG", "brand_model": "Depósito de agua contra incendios (Málaga)",
     "folders": ["DEPOSITO AGUA CONTRA INCENDIOS-MALAGA"]},
    {"code": "DOLLYS", "brand_model": "Dollys",
     "folders": ["DOLLYS"]},
    {"code": "COMOLI", "brand_model": "Oruga Comoli (n.º 1588006604)",
     "folders": ["MAQUINARIA OTROS/COMOLI/ORUGA 1588006604"]},
    {"code": "BOBCAT", "brand_model": "Barredora Bobcat",
     "folders": ["VARIOS/BARREDORA BOBCAT"]},
    {"code": "CHORREO", "brand_model": "Máquina de chorreo de arena",
     "folders": ["VARIOS/MAQUINA CHORREO ARENA"]},
    {"code": "CARGADORA", "brand_model": "Cargadora de ruedas",
     "folders": ["CARGADORA RUEDAS"]},
    {"code": "CANASTA", "brand_model": "Canasta colgada",
     "folders": ["CANASTA COLGADA"]},
    {"code": "PARALELAS", "brand_model": "Paralelas de deslizamiento hidráulico",
     "folders": ["MAQUINARIA ESPECIAL/PARALELAS DE DESLIZAMIENTO HIDRHULICO"]},
    {"code": "SEPBEZABALA", "brand_model": "Separador Bezabala homologado",
     "folders": ["SEPARADOR BEZABALA HOMOLOGADO"]},
]


def _folder_query(folder):
    """
    The folder itself and everything below it.
    ---
    La carpeta y todo lo que cuelga de ella.
    """
    full = ROOT + folder
    return Q(parent_path=full) | Q(parent_path__startswith=full + "/")


def _normalized(text):
    """
    Upper-case, no spaces/dashes/dots (plate comparison).
    ---
    Mayúsculas, sin espacios/guiones/puntos (comparar matrículas).
    """
    return re.sub(r"[\s.\-_]", "", (text or "").upper())


class Command(BaseCommand):
    help = (
        "H30 (S117) -- Fase 2 de MAQUINAS: alta desde consola de las "
        "maquinas que faltaban y asignacion de sus documentos. Dry-run "
        "por defecto, --apply para escribir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, com-standards 0bis).",
        )

    def _log(self, message):
        self._log_plain("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes):
        reference = (
            MachineAsset.objects
            .filter(company_code=REFERENCE_COMPANY_CODE)
            .select_related("company")
            .first()
        )
        if not reference:
            self._log("ERROR: no hay ninguna maquina GRA de referencia -- nada que hacer.")
            return
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        total = len(MACHINES)
        self._log(
            "MODO: %s -- %d maquinas de la tabla confirmada por Miguel Angel"
            % ("APLICAR (escribe)" if apply_changes else "DRY-RUN (no escribe nada)", total)
        )

        created = reused = assigned = 0
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, spec in enumerate(MACHINES, start=1):
            query = Q()
            for folder in spec["folders"]:
                query |= _folder_query(folder)
            entries = [
                e for e in DocumentIndexEntry.objects.filter(
                    query, bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                    domain_object_id__isnull=True,
                    deleted_at__isnull=True, purged_at__isnull=True,
                )
                if not spec.get("name_contains")
                or _normalized(spec["name_contains"]) in _normalized(e.name)
            ]

            existing = MachineAsset.objects.filter(code__iexact=spec["code"]).first()
            if existing:
                reused += 1
                action = "YA EXISTE (se reutiliza, pk=%d)" % existing.pk
            else:
                created += 1
                action = "SE DA DE ALTA"
            self._log(
                "%s %s -- %s -- %d documento(s) sin maquina en %s"
                % (action, spec["code"], spec["brand_model"], len(entries),
                   " + ".join(spec["folders"]))
            )
            for entry in entries:
                self._log("    -> %s/%s" % (entry.parent_path, entry.name))
            assigned += len(entries)

            if apply_changes:
                with transaction.atomic():
                    asset = existing or MachineAsset.objects.create(
                        company=reference.company,
                        company_code=reference.company_code,
                        company_name=reference.company_name,
                        code=spec["code"],
                        plate=spec.get("plate", ""),
                        brand_model=spec["brand_model"],
                    )
                    for entry in entries:
                        entry.domain_content_type = machine_ct
                        entry.domain_object_id = asset.pk
                        entry.save(update_fields=[
                            "domain_content_type", "domain_object_id",
                        ])

            if time.monotonic() - last_beat >= 30 or index == total or index % 5 == 0:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (datetime.now() + timedelta(seconds=eta_seg)).strftime("%H:%M:%S")
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s)"
                    % (index, total, index * 100 // total,
                       int(eta_seg // 60), int(eta_seg % 60), hora_fin)
                )

        self._log_plain("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    maquinas dadas de alta: %d" % created)
        self._log_plain("    maquinas que ya existian (reutilizadas): %d" % reused)
        self._log_plain("    documentos asignados: %d" % assigned)
        self._log_plain(
            "    empresa por defecto: %s (%s) -- familia vacia, a completar "
            "por Yolanda en la ficha" % (reference.company_code, reference.company_name)
        )
