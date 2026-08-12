# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/audit_mandatory_documents.py
"""
H30 (S49). Informe de cobertura de documentacion obligatoria por
MACHINE activa -- responde directamente a la pregunta real de Miguel
Angel en S49: "que ninguna maquina este sin esos documentos
obligatorios", detectada en produccion tras ver un vehiculo con ITV
vigente hasta 2027 pero sin PERMISO_CIRCULACION localizado.

SOLO LECTURA. No escribe nada en la base de datos -- es un informe.

Familia normativa por PREFIJO de `MachineAsset.code` (A/B/Z/H/MK/P/T/
V/S), confirmada por Miguel Angel en esta misma sesion (S49) --
DISTINTA del campo `MachineAsset.family` (texto libre del catalogo de
S043, ej. "MOVILES", "PLATAFOR"). REMOLQUE/GONDOLA (R/G) y Vehiculos
de Empresa (turismos, por matricula, sin prefijo de letra) quedan
fuera de alcance de H30 segun S47.

Lista de tipos obligatorios: PRIMER CORTE basado en la investigacion
normativa real (RD 837/2003 grua movil, RD 1215/1997+1644/2008 resto,
RD 836/2003 grua torre) hecha al abrir esta sesion, acotada a los
tipos que ya existen en el catalogo cerrado real. Deliberadamente NO
incluye IPO/ITC (significado exacto en el archivo de Grupo Alvarez
sin confirmar todavia por Miguel Angel) -- ajustar aqui, nunca en
otro sitio, en cuanto se confirme.
"""
from collections import defaultdict
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset

# prefijo de MachineAsset.code -> lista de DocumentTypeCatalog.code
# obligatorios (primer corte, ajustable). "MK" retirado: verificado con
# datos reales (S49) que las gruas torre sobre camion (p.ej. "GRUA
# TORRE SOBRE CAMION MK80") estan codificadas dentro de la familia A
# (A57, A63, A64, A67...), MK es solo parte del nombre del modelo, no
# un prefijo de codigo real.
MANDATORY_BY_PREFIX = {
    # IPO/ITC anadidos S50 tras confirmar su significado real
    # (busqueda + datos reales del corpus): IPO = Inspeccion
    # Periodica Obligatoria, el acta de inspeccion oficial de la
    # grua (equivalente al ITV pero para aparatos de elevacion,
    # ITC MIE-AEM-4/RD 837/2003); ITC = la referencia normativa que
    # acompana esa inspeccion. Ambos ya existian como DocumentType
    # Catalog (ids 19 y 16) y ya funcionaban en clasificacion
    # (391/414 IPO y 66/135 ITC ya clasificados antes de esta
    # sesion) -- solo faltaba incluirlos aqui. Acotado a la familia
    # A (grúas móviles autopropulsadas): 100% de las coincidencias
    # reales de IPO y el grueso de ITC viven en "GRUAS MOVILES (A)";
    # la unica excepcion real (una carretilla, familia T) es un
    # unico archivo sin clasificar, no evidencia suficiente para
    # extender la obligatoriedad a esa familia.
    # Fusionados S50 (migracion 0031) en un solo codigo IPO_ITC: por
    # contenido real (ver sample_known_type_ocr_text) son el mismo
    # documento, el acta de inspeccion periodica de la grua movil.
    "A": ["PERMISO_CIRCULACION", "FICHA_TECNICA", "ITV", "SEGURO", "OCA", "RAE", "IPO_ITC"],
    "B": ["PERMISO_CIRCULACION", "FICHA_TECNICA", "ITV", "SEGURO", "C_ADECUACION"],
    "Z": ["CE", "C_ADECUACION", "SEGURO"],
    "H": ["CE", "SEGURO"],
    "P": ["PERMISO_CIRCULACION", "FICHA_TECNICA", "ITV", "SEGURO", "TARJETA_TRANSPORTE"],
    "T": ["CE", "SEGURO"],
    "V": ["CE", "SEGURO"],
    "S": ["CE"],
}
# Solo letra(s) + digitos, nunca solo letras -- corregido S49 tras
# detectar falsos positivos reales (ADMINIST/ADOLFO/BEN/PAOLA/
# PERSONAL/VARIOS/VENTA: carpetas administrativas o de centros de
# gasto que empiezan por la misma letra que un prefijo real de
# familia, ya excluidas del alcance de H30 desde S47 -- nunca son
# maquinas). Prefijos de mas de una letra primero, para que ninguno de
# una letra los recorte mal (no hay hoy ninguno de mas de una letra,
# pero se deja el orden por si aparece en el futuro).
_PREFIXES_BY_LENGTH = sorted(MANDATORY_BY_PREFIX, key=len, reverse=True)
_CODE_RE = re.compile(
    r"^(%s)\d+$" % "|".join(re.escape(p) for p in _PREFIXES_BY_LENGTH)
)


def _family_prefix(code):
    code_upper = (code or "").strip().upper()
    match = _CODE_RE.match(code_upper)
    if not match:
        return None
    return match.group(1)


class Command(BaseCommand):
    help = (
        "H30 (S49) -- informe de cobertura de documentacion "
        "obligatoria por MachineAsset activa. Solo lectura."
    )

    def handle(self, *args, **options):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        machines = MachineAsset.objects.filter(is_active=True).order_by("code")

        # tipo -> {machine_pk} con al menos una fila vigente
        present = defaultdict(set)
        qs = DocumentIndexEntry.objects.filter(
            domain_content_type=machine_ct,
            document_type__isnull=False,
            deleted_at__isnull=True, purged_at__isnull=True,
            is_obsolete=False,
        ).values_list("domain_object_id", "document_type__code")
        for machine_pk, code in qs:
            present[code].add(machine_pk)

        stats = {"sin_prefijo_reconocido": 0, "completas": 0, "con_huecos": 0}
        total_gaps = 0

        for machine in machines:
            prefix = _family_prefix(machine.code)
            if prefix is None:
                stats["sin_prefijo_reconocido"] += 1
                continue
            required = MANDATORY_BY_PREFIX[prefix]
            missing = [
                code for code in required
                if machine.pk not in present.get(code, set())
            ]
            if missing:
                stats["con_huecos"] += 1
                total_gaps += len(missing)
                self.stdout.write(
                    "HUECO  [%s] %s (familia %s) -> falta: %s"
                    % (machine.code, machine.type_name or "", prefix,
                       ", ".join(missing))
                )
            else:
                stats["completas"] += 1

        self.stdout.write("=== RESUMEN ===")
        self.stdout.write("    maquinas activas totales: %d" % machines.count())
        self.stdout.write(
            "    sin prefijo reconocido (fuera de A/B/Z/H/P/T/V/S): %d"
            % stats["sin_prefijo_reconocido"]
        )
        self.stdout.write("    completas: %d" % stats["completas"])
        self.stdout.write("    con huecos: %d" % stats["con_huecos"])
        self.stdout.write("    total huecos (suma): %d" % total_gaps)
