# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/calibrate_fase_a_keywords.py
"""
H30 (S48) -- calibracion, SOLO LECTURA, del diccionario heuristico de
la Fase A del recorrido dirigido (ver ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md,
"Hoja de Ruta para la Siguiente Sesion", punto 1).

El diccionario real de S46/S47 nunca quedo persistido como codigo --
vivio solo en consultas puntuales de esas sesiones y en la narrativa
del anexo (que solapes se resolvieron, que falsos positivos se
descartaron). Este comando reconstruye candidatos de palabra clave por
tipo del catalogo cerrado (DocumentTypeCatalog, 59 tipos activos,
consultados en S48) y los verifica contra el corpus real -- nunca
escribe nada, solo cuenta coincidencias y muestra ejemplos reales para
que Miguel Angel confirme antes de que un comando separado (Fase A de
verdad) aplique document_type/domain_object en bulk.

Separa candidatos "seguros" (frases especificas, poco riesgo de falso
positivo) de acronimos cortos de riesgo real ya confirmado en S46
(OCA dentro de OCAÑA, CAP dentro de INCAPACIDAD/CAPACITACION) -- estos
ultimos solo se reportan, nunca se dan por buenos aqui.

BAJA_PERSONAL / PARTE_BAJA_MEDICA / INVESTIGACION_ACCIDENTE quedan
deliberadamente fuera de los candidatos por palabra: S47 confirmo que
se separan por carpeta real, nunca por la palabra "BAJA" sola.
"""
import re
import unicodedata

from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.models import DocumentIndexEntry

MACHINE_ROOT = "DOC. MAQUINAS"
PERSONAL_ROOT = "DOC. PERSONAL"
BUCKET = "cgs_grupo_alvarez"

# domain -> {code: [candidatos]}
CANDIDATES_SAFE = {
    "MACHINE": {
        "BAJA_DEFINITIVA": ["BAJA DEFINITIVA"],
        "BAJA_TEMPORAL": ["BAJA TEMPORAL"],
        "CERT_MANTENIMIENTO": [
            "CERTIF MANTENIMIENTO", "CERTIFICADO MANTENIMIENTO",
        ],
        "CERT_NO_TARJ_TTES": ["CERT_NO_TARJ_TTES"],
        "CERT_REVISION": ["CERTIFICADO REVISION", "CERTIF REVISION"],
        "CONTRATO_COMPRAVENTA": ["CONTRATO COMPRAVENTA", "COMPRAVENTA"],
        "C_ADECUACION": ["ADECUACION"],
        "DECLARACION_HOMOLOGACION": ["HOMOLOGACION"],
        "DNI_COMPRADOR": ["DNI COMPRADOR"],
        "DOC_BAJA_DEFINITIVA": ["DESGUACE"],
        "DOC_VENTA": ["VENTA"],
        "FACTURA_COMPRA": ["FACTURA COMPRA"],
        "FICHA_TECNICA": ["FICHA TECNICA"],
        "ITV": ["ITV"],
        "JUSTIFICANTE_TRANSFERENCIA": ["JUSTIFICANTE_TRANSFERENCIA"],
        "LEASING": ["LEASING"],
        "LIBRO_HISTORIAL": ["LIBRO HISTORIAL"],
        "MANUAL_DESPIECE": ["DESPIECE"],
        "MANUAL_USO": ["MANUAL USO"],
        "PERMISO_CIRCULACION": ["PERMISO CIRCULACION"],
        "PRESTAMO": ["PRESTAMO"],
        "PROFORMA": ["PROFORMA"],
        "RECIBO_LEASING": [
            "CUOTA LEASING", "RECIBO LEASING", "FACTURA LEASING",
        ],
        "RECIBO_SENAL_COMPRA": ["RECIBO_SENAL_COMPRA"],
        "SOLICITUD_ADMINISTRATIVA": ["SOLICITUD"],
        "TABLA_DE_CARGA": ["TABLA CARGA"],
        "TARJETA_TRANSPORTE": ["TARJETA TRANSPORTE"],
    },
    "BOTH": {
        "MANDATO": ["MANDATO"],
        "SEGURO": ["SEGURO", "REC SEG", "REC POL"],
        "TACOGRAFO": ["TACOGRAFO"],
    },
    "PERSONAL": {
        "ALTA_MEDICA": ["ALTA MEDICA"],
        "ALTA": ["ALTA"],
        "CARNET_CONDUCIR": ["CARNET CONDUCIR", "CARNE CONDUCIR"],
        "CONTRATO": ["CONTRATO LABORAL"],
        "CURSO": ["CURSO"],
        "DNI": ["DNI"],
        "ENTREGA_INFORMACION": ["ENTREGA INFORMACION"],
        "EXCEDENCIA": ["EXCEDENCIA"],
        "FORMACION": ["FORMACION"],
        "MOD_145": ["MODELO 145"],
        "NOMINA": ["NOMINA"],
        "PAGO_CORRIENTE": ["PAGO CORRIENTE"],
        "RECONOCIMIENTO_MEDICO": ["RECONOCIMIENTO MEDICO"],
        "SEG_SOCIAL": ["SEGURIDAD SOCIAL"],
        "VACACIONES": ["VACACIONES"],
        # EPIS deliberadamente FUERA (S48, correccion de Miguel Angel):
        # los documentos de EPI se consumen hacia EpiDelivery/
        # EpiReview (modelo propio de S47), nunca se clasifican como
        # document_type=EPIS por este recorrido heuristico -- flujo
        # distinto. Sin esta exclusion, ademas, "EPIS ALTA
        # VISIBILIDAD" habria colisionado en falso con ALTA (ver
        # EXCLUSIONS mas abajo).
    },
}

# Exclusiones por falso positivo real, detectado contra el corpus
# (mismo patron que "BAJA TENSION" excluido de BAJA_PERSONAL en S46).
# clave (domain, code, phrase) -> lista de frases que, si aparecen en
# el nombre, anulan esa coincidencia aunque el patron de palabra
# suelta hubiera matcheado.
EXCLUSIONS = {
    ("PERSONAL", "ALTA", "ALTA"): ["ALTA VISIBILIDAD"],
}

CANDIDATES_RISKY = {
    "MACHINE": {
        "CE": ["CE"], "IPO": ["IPO"], "ITC": ["ITC"],
        "OCA": ["OCA"], "RAE": ["RAE"],
    },
    "PERSONAL": {"CAP": ["CAP"], "CSS": ["CSS"], "IDC": ["IDC"]},
}


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _build_pattern(phrase):
    parts = [re.escape(w) for w in phrase.split(" ")]
    body = r"[ _\-\.]+".join(parts)
    # Corregido S48: \b trata "_" como caracter de palabra, asi que
    # nunca detectaba un candidato pegado entre guiones bajos (p. ej.
    # "CERT_NO_TARJ_TTES" dentro de "A29_CERT_NO_TARJ_TTES_20230314"
    # -- verificado con datos reales que \b fallaba ahi). Un lookaround
    # que solo trata [A-Z0-9] como caracter de palabra trata "_"/"-"/
    # "."/espacio como frontera valida por igual.
    return re.compile(r"(?<![A-Z0-9])" + body + r"(?![A-Z0-9])")


def _files_for_domain(domain):
    roots = []
    if domain in ("MACHINE", "BOTH"):
        roots.append(MACHINE_ROOT)
    if domain in ("PERSONAL", "BOTH"):
        roots.append(PERSONAL_ROOT)
    cond = Q()
    for root in roots:
        cond |= Q(parent_path=root) | Q(parent_path__startswith=root + "/")
    return DocumentIndexEntry.objects.filter(
        cond, bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        document_type__isnull=True,
    ).only("id", "name", "parent_path")


class Command(BaseCommand):
    help = (
        "H30 (S48) -- calibracion de solo lectura del diccionario "
        "heuristico de Fase A. No escribe nada en la base de datos."
    )

    def _run(self, candidates_dict, label):
        self.stdout.write("========== %s ==========" % label)
        match_index = {}
        for domain, codes in candidates_dict.items():
            entries = list(_files_for_domain(domain))
            norm_names = [
                (e, _strip_accents(e.name).upper()) for e in entries
            ]
            for code, phrases in codes.items():
                for phrase in phrases:
                    pattern = _build_pattern(_strip_accents(phrase).upper())
                    excl_phrases = EXCLUSIONS.get((domain, code, phrase), [])
                    excl_patterns = [
                        _build_pattern(_strip_accents(p).upper())
                        for p in excl_phrases
                    ]
                    hits = [
                        e for e, n in norm_names
                        if pattern.search(n)
                        and not any(ep.search(n) for ep in excl_patterns)
                    ]
                    self.stdout.write(
                        "%s | %-28s | %-30s | %d coincidencias"
                        % (domain, code, phrase, len(hits))
                    )
                    for e in hits[:3]:
                        self.stdout.write(
                            "    ej: [%s] %s" % (e.parent_path, e.name)
                        )
                    for e in hits:
                        match_index.setdefault(e.id, []).append(
                            (code, phrase)
                        )

        overlaps = {
            eid: codes for eid, codes in match_index.items()
            if len(set(c for c, _p in codes)) > 1
        }
        self.stdout.write(
            "--- SOLAPES DETECTADOS (mismo archivo, mas de un tipo "
            "candidato): %d ---" % len(overlaps)
        )
        shown = 0
        for eid, codes in overlaps.items():
            if shown >= 15:
                self.stdout.write(
                    "    ... (%d solapes mas, no mostrados)"
                    % (len(overlaps) - shown)
                )
                break
            entry = DocumentIndexEntry.objects.get(pk=eid)
            self.stdout.write(
                "    [%s] %s -> %s"
                % (entry.parent_path, entry.name, codes)
            )
            shown += 1

        # Agregacion por PAR de tipos -- volumen real, no archivo a
        # archivo, para decidir prioridades con datos (S48). Incluye
        # hasta 3 ejemplos reales por par -- decidir prioridad sin ver
        # nombres reales seria interpretacion propia, prohibido por
        # directriz 4.8.
        from collections import Counter, defaultdict
        pair_counts = Counter()
        pair_examples = defaultdict(list)
        for eid, codes in overlaps.items():
            distinct_codes = sorted(set(c for c, _p in codes))
            for i in range(len(distinct_codes)):
                for j in range(i + 1, len(distinct_codes)):
                    pair = (distinct_codes[i], distinct_codes[j])
                    pair_counts[pair] += 1
                    if len(pair_examples[pair]) < 3:
                        pair_examples[pair].append(eid)
        self.stdout.write("--- SOLAPES AGREGADOS POR PAR DE TIPOS ---")
        for pair, count in pair_counts.most_common():
            self.stdout.write(
                "    %s <-> %s : %d archivos" % (pair[0], pair[1], count)
            )
            for eid in pair_examples[pair]:
                entry = DocumentIndexEntry.objects.get(pk=eid)
                self.stdout.write(
                    "        ej: [%s] %s" % (entry.parent_path, entry.name)
                )

    def handle(self, *args, **options):
        self._run(CANDIDATES_SAFE, "CANDIDATOS SEGUROS")
        self._run(CANDIDATES_RISKY, "ACRONIMOS DE RIESGO -- SOLO REVISION")
