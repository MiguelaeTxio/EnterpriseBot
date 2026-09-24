# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/classify_untyped_machine_text.py
"""
H30 (S118), punto 7 de la hoja de ruta -- PASO B: clasificación de los
documentos SIN TIPO de máquinas ACTIVAS sobre el texto ya guardado en
`ocr_text` por el paso A (`read_untyped_machine_text`). Gratis y
repetible: no descarga nada ni llama a Cloud Vision.

Criterio: el tipo se decide por la CABECERA (primeros HEADER_CHARS
caracteres normalizados), nunca por el cuerpo -- lección de S50: un
cuerpo largo menciona "ITV" o "CE" de pasada sin SER ese documento.
Marcadores sacados de frases reales repetidas en el texto de estos
mismos 918 documentos (S118). Orden = prioridad: gana el primero.

Documentos de PERSONAS archivados en carpetas de vehículos (DNI, altas
de la Seguridad Social...), regla de Miguel Ángel (S118): "si existe
la ficha de esas personas y son trabajadores activos o dueños, se
mueven [...] hay que ver si son los documentos vigentes o no. Y si no
son de personas activas, directamente a la papelera." La persona se
identifica por DNI/NIE leído en el texto (`resolve_person_identity`,
identificador duro) o, si no, por el nombre del archivo con la regla
de S69 (`resolve_person_by_name_count`). Los dueños que no constan
como trabajador activo se indican con --owner-pks.

Facturas: compra o venta según el nombre del archivo o quién figura
como cliente en la cabecera; si no se puede decidir, queda sin
resolver (nunca se adivina).

DRY-RUN por defecto; --apply escribe. Nunca toca GCS (4.12). Log
propio con heartbeat y ETA (com-standards 0bis/0ter).
---
H30 (S118), roadmap item 7 -- STEP B: classify untyped documents of
active machines from the cached `ocr_text`, by header only. Personal
documents filed under vehicles are moved to an active person's record
or trashed, per Miguel Ángel's rule.
"""
import re
import time
import unicodedata
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils import timezone

from document_explorer.classification_service import (
    NAME_MATCH_UNIQUE,
    resolve_person_by_name_count,
    resolve_person_identity,
)
from document_explorer.date_verification_service import (
    extract_dni_front_expiry,
    extract_dni_mrz_expiry,
)
from document_explorer.models import (
    DocumentIndexEntry,
    DocumentTypeCatalog,
    PersonIdentity,
)
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
HEADER_CHARS = 800
COMPANY_NAMES = ("GRUAS ADOLFO ALVAREZ", "TRANSGRUAL", "ASISTENCIA Y GRUAS")
COMPANY_TAX_IDS = ("B29405040", "B92493022")
# Entidades que figuran como cliente cuando la máquina se compra con
# leasing (la factura de compra se emite al banco, la máquina es
# nuestra) -- casos reales de S118: Cajamar, BBVA, Caixabank, Abanca.
LEASING_BANKS = (
    "CAJAMAR", "BANCO BILBAO VIZCAYA", "BBVA", "CAIXABANK", "ABANCA",
    "SANTANDER", "BANKINTER", "DE LAGE LANDEN", "IBERCAJA", "UNICAJA",
    "SABADELL",
)
# Aseguradoras: un adeudo bancario domiciliado de una de ellas es el
# recibo del seguro de la máquina.
INSURERS = (
    "ALLIANZ", "GENERALI", "MAPFRE", "HELVETIA", "AXA", "ZURICH",
    "MUTUA", "REALE", "CASER", "LIBERTY", "PELAYO", "PLUS ULTRA",
)

# Formato europeo del permiso de circulación (casillas P.1, P.2, C.1.1).
EU_REGISTRATION_RE = re.compile(
    r"\bP\.1\b.*\bP\.2\b.*\bC\.1\.1\b|\bC\.1\.1\b.*\bP\.3\b"
    r"|\bB F\.1\b.*\bH F\.2\b",
)

# (código, frases de cabecera) -- el orden es la prioridad.
MACHINE_HEADER_MARKERS = [
    ("SEGURO", [
        "NOTA DE ADEUDO", "RECIBO PRIMA", "RECIBO DE PRIMA",
        "FACTURACION SEGUROS SUSCRITOS", "DETALLE DEL MOVIMIENTO",
        "COMUNICACION OPERACION EN CUENTA",
    ]),
    ("POLIZA_SEGURO", [
        "CONDICIONES PARTICULARES", "POLIZA DE SEGURO",
        "CONDICIONES GENERALES DEL SEGURO",
    ]),
    ("CARTA_VERDE", ["CERTIFICADO INTERNACIONAL DE SEGURO", "GREEN CARD"]),
    ("CERTIFICADO_SEGURO", [
        "CERTIFICADO DE SEGURO", "TIENE CONTRATADO", "SE ENCUENTRA ASEGURADO",
        "CORREDURIA DE SEGUROS", "VERSICHERUNGSBESCHEINIGUNG",
        "HELVETIA FLOTAS",
    ]),
    ("IPO_ITC", [
        "ACTA DE INSPECCION PERIODICA", "INSPECCION PERIODICA OFICIAL",
        "INSPECCION PERIODICA DE GRUAS", "TIPO DE INSPECCION",
        "DETALLES DE LA GRUA", "HAUPTUNTERSUCHUNG",
    ]),
    ("OCA", ["OCA GLOBAL", "ACREDITADO POR ENAC", "ORGANISMO DE CONTROL"]),
    ("LIBRO_HISTORIAL", [
        "REVISIONES TECNICAS PERIODICAS", "REGISTRO DE MANTENIMIENTO",
    ]),
    ("CERT_MANTENIMIENTO", [
        "REALIZA TODAS SUS REVISIONES DE MANTENIMIENTO",
        "COMO EMPRESA CONSERVADORA",
    ]),
    ("AUTORIZACION_PROVISIONAL_CIRCULACION", [
        "AUTORIZACION PROVISIONAL DE CIRCULACION",
        "AUTORIZACION DE CIRCULACION REF",
    ]),
    ("PERMISO_CIRCULACION", [
        "DOCUMENTO VALIDO ACOMPANA", "PERMISO DE CIRCULACION",
    ]),
    ("ITV", ["INSPECCIONES TECNICAS"]),
    ("RAE", [
        "FICHA TECNICA DESCRIPTIVA DE GRUAS", "RAE4",
        "DOCUMENTO ELECTRONICO EN LA",
    ]),
    ("FICHA_TECNICA", [
        "CLASIFICACION DEL VEHICULO", "TARJETA DE INSPECCION TECNICA",
        "EJEMPLAR PARA EL USUARIO", "MATRICULA CERTIFICADO N",
        "NO VALIDO PARA CIRCULAR",
    ]),
    ("CE", [
        "DECLARACION DE CONFORMIDAD", "DECLARATION DE CONFORMITE",
        "DECLARATION OF CONFORMITY", "KONFORMITATSERKLARUNG",
    ]),
    ("C_ADECUACION", [
        "CERTIFICADO DE ADECUACION",
        "CONDICIONES DE SEGURIDAD Y SALUD EN LAS MAQUINAS",
        "R.D. 1215", "RD 1215", "REAL DECRETO 1215",
    ]),
    ("TABLA_DE_CARGA", [
        "TABLAS DE CARGA", "TABLA DE CARGA", "DIAGRAMA DE CARGA",
        "DIAGRAMA DE ALCANCE",
    ]),
    ("CAMBIO_TITULARIDAD", [
        "CAMBIO DE TITULARIDAD", "TRANSFERENCIA DE TITULARIDAD",
        "NOTIFICACION DE VENTA",
    ]),
    ("BAJA_DEFINITIVA", [
        "BAJA DEFINITIVA", "TRATAMIENTO RESIDUAL",
        "CERTIFICADO DE DESTRUCCION",
    ]),
    ("BAJA_TEMPORAL", ["BAJA TEMPORAL"]),
    ("INFORME_VEHICULO_DGT", [
        "INFORME DEL VEHICULO", "INFORME DE VEHICULO",
        "HISTORIAL DEL VEHICULO",
    ]),
    ("REFORMA_VEHICULO", ["REFORMA DE IMPORTANCIA", "PROYECTO TECNICO"]),
    ("TARJETA_TRANSPORTE", [
        "TARJETA DE TRANSPORTE", "AUTORIZACION DE TRANSPORTE",
    ]),
    ("REV_TACOGRAFO", ["TACOGRAFO"]),
    ("IVTM", ["IMPUESTO SOBRE VEHICULOS DE TRACCION MECANICA"]),
    ("CERTIFICADO_PODERES", [
        "DOCUMENTO DE REPRESENTACION DE PERSONAS JURIDICAS",
        "PODER GENERAL", "PROCURACAO", "APODERAMIENTO",
    ]),
    ("LEASING", [
        "ARRENDATARIO FINANCIERO", "ARRENDAMIENTO FINANCIERO", "LEASING",
    ]),
    ("CUADRO_AMORTIZACION", ["CUADRO DE AMORTIZACION"]),
    ("CONTRATO_COMPRAVENTA", [
        "CONTRATO DE COMPRAVENTA", "CONTRATO DE COMPRA VENTA",
    ]),
    ("PROFORMA", ["PRESUPUESTO", "PROFORMA", "OFERTA"]),
    ("JUSTIFICANTE_TRANSFERENCIA", [
        "JUSTIFICANTE DE TRANSFERENCIA",
        "JUSTIFICANTE PROVISIONAL DE TRANSFERENCIA",
        "ORDEN DE TRANSFERENCIA", "TRANSFERENCIA NUMERO DE REFERENCIA",
    ]),
    ("SANCION_TRAFICO", [
        "BOLETIN DE DENUNCIA", "IDENTIFICACION DEL CONDUCTOR",
    ]),
    ("FACTURA", ["FACTURA"]),
    ("MANUAL_USO", [
        "MANUAL DE INSTRUCCIONES", "MANUAL DE USO", "MANUAL DEL OPERADOR",
        "OPERATOR'S MANUAL", "MANUAL DE SEGURIDAD",
    ]),
    ("MANUAL_DESPIECE", ["CATALOGO DE PIEZAS", "DESPIECE", "SPARE PARTS"]),
]

# Cabeceras de documento de PERSONA archivado bajo un vehículo.
PERSON_HEADER_MARKERS = [
    ("DNI", ["DOCUMENTO NACIONAL DE IDENTIDAD"]),
    ("ALTA", [
        "RESOLUCION SOBRE RECONOCIMIENTO DE ALTA",
        "RESOLUCION DE ALTA, BAJA O VARIACION DE DATOS DEL TRABAJ",
    ]),
]

DNI_RE = re.compile(r"\b(\d{8})\s?-?\s?([A-Z])\b")
NIE_RE = re.compile(r"\b([XYZ])\s?-?(\d{7})\s?-?([A-Z])\b")
# "APELLIDO APELLIDO, NOMBRE" -- nombre de archivo de un alta.
COMMA_NAME_RE = re.compile(r"^\s*([A-Z]+)\s+([A-Z]+)?\s*,\s*([A-Z]+)")


def normalize(text):
    """
    Uppercase, strip accents and collapse whitespace.
    ---
    Mayúsculas, sin acentos, espacios colapsados (incluidos saltos).
    """
    plain = unicodedata.normalize("NFKD", text or "").encode(
        "ascii", "ignore",
    ).decode()
    return re.sub(r"\s+", " ", plain.upper())


def match_markers(header, markers):
    """
    First marker code whose phrase appears in the header, or None.
    ---
    Primer código cuyo marcador aparece en la cabecera, o None.
    """
    for code, phrases in markers:
        if any(phrase in header for phrase in phrases):
            return code
    return None


def resolve_invoice(entry_name, header):
    """
    FACTURA_COMPRA / FACTURA_VENTA, or None when it cannot be decided.
    ---
    Compra si una de nuestras empresas figura como CLIENTE; venta si el
    nombre lo dice o si la cabecera empieza por una de nuestras
    empresas. Si no, None -- nunca se adivina.
    """
    name = normalize(entry_name)
    if "VENTA" in name:
        return "FACTURA_VENTA"
    if "COMPRA" in name:
        return "FACTURA_COMPRA"
    for match in re.finditer(r"CLIENTE", header):
        window = header[match.end():match.end() + 150]
        if any(company in window for company in COMPANY_NAMES):
            return "FACTURA_COMPRA"
    if any(company in header[:80] for company in COMPANY_NAMES):
        return "FACTURA_VENTA"
    # S118, casos reales: el proveedor encabeza la factura y una de
    # nuestras empresas (o el banco del leasing) figura como destinatario
    # más abajo -- es una compra.
    if any(tax_id in header for tax_id in COMPANY_TAX_IDS) or any(
        company in header for company in COMPANY_NAMES
    ) or any(bank in header for bank in LEASING_BANKS):
        return "FACTURA_COMPRA"
    return None


def resolve_person(text, entry_name):
    """
    Return (person, how) from a DNI/NIE in the text, or the file name.
    ---
    Persona por DNI/NIE leído en el texto (identificador duro) o, si
    no, por "APELLIDO APELLIDO, NOMBRE" en el nombre del archivo con la
    regla de S69. (None, motivo) si no se resuelve.
    """
    for number, letter in DNI_RE.findall(text):
        person = resolve_person_identity(number + letter)
        if person:
            return person, "DNI %s%s" % (number, letter)
    for prefix, number, letter in NIE_RE.findall(text):
        person = resolve_person_identity(prefix + number + letter)
        if person:
            return person, "NIE %s%s%s" % (prefix, number, letter)
    name_match = COMMA_NAME_RE.match(normalize(entry_name))
    if name_match:
        first_surname, second_surname, given = name_match.groups()
        status, person = resolve_person_by_name_count(
            given, first_surname, second_surname,
        )
        if status == NAME_MATCH_UNIQUE:
            return person, "nombre de archivo"
        return None, "nombre de archivo sin ficha única (%s)" % status
    return None, "sin DNI ni nombre reconocible"


class Command(BaseCommand):
    help = (
        "H30 (S118) -- paso B del punto 7: tipo de los documentos sin "
        "tipo de maquinas activas por la cabecera del texto guardado. "
        "Dry-run por defecto, --apply para escribir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--owner-pks", default="",
            help="PersonIdentity pk de duenos (cuentan como activos), "
                 "separados por coma.",
        )
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        self._log_plain(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message),
        )

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        owner_pks = {
            int(pk) for pk in options["owner_pks"].split(",") if pk.strip()
        }
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"], owner_pks)
        finally:
            self._log_handle.close()

    def _run(self, apply_changes, owner_pks):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        catalog = {
            dt.code: dt for dt in DocumentTypeCatalog.objects.filter(
                is_active=True,
            )
        }
        active_pks = list(MachineAsset.objects.filter(
            is_active=True,
        ).values_list("pk", flat=True))
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=True,
            domain_content_type=machine_ct,
            domain_object_id__in=active_pks,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).exclude(ocr_text="").order_by("id"))
        total = len(entries)
        self._log(
            "PASO B -- MODO: %s -- %d documentos sin tipo de maquinas "
            "activas con texto guardado (duenos por --owner-pks: %s)" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)",
                total, sorted(owner_pks) or "ninguno",
            )
        )

        by_type = {}
        unresolved = []
        person_moves, person_trash = [], []
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, entry in enumerate(entries, start=1):
            full = normalize(entry.ocr_text)
            header = full[:HEADER_CHARS]

            person_code = match_markers(header, PERSON_HEADER_MARKERS)
            if person_code:
                self._handle_person(
                    entry, full, person_code, owner_pks, person_ct,
                    catalog, apply_changes, person_moves, person_trash,
                )
            else:
                code = match_markers(header, MACHINE_HEADER_MARKERS)
                if code in (None, "FACTURA") and "ADEUDO POR DOMICILIACION" \
                        in header and any(
                            insurer in header or insurer in normalize(
                                entry.name,
                            ) for insurer in INSURERS):
                    code = "SEGURO"
                if code is None and EU_REGISTRATION_RE.search(header):
                    code = "PERMISO_CIRCULACION"
                if code == "FACTURA":
                    code = resolve_invoice(entry.name, header)
                    if code is None:
                        unresolved.append(
                            (entry, "FACTURA sin compra/venta decidible"),
                        )
                        code = "-"
                if code is None:
                    unresolved.append((entry, "sin marcador de cabecera"))
                elif code != "-":
                    if code not in catalog:
                        unresolved.append(
                            (entry, "tipo %s no esta en el catalogo" % code),
                        )
                    else:
                        by_type.setdefault(code, []).append((entry, header))
                        if apply_changes:
                            DocumentIndexEntry.objects.filter(
                                pk=entry.pk,
                            ).update(document_type=catalog[code])

            if index % 25 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (
                    datetime.now() + timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- tipados=%d, personas_mover=%d, personas_papelera=%d,"
                    " sin_resolver=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        sum(len(v) for v in by_type.values()),
                        len(person_moves), len(person_trash), len(unresolved),
                    )
                )

        self._summary(
            apply_changes, total, by_type, person_moves, person_trash,
            unresolved,
        )

    def _handle_person(self, entry, full, code, owner_pks, person_ct,
                       catalog, apply_changes, person_moves, person_trash):
        """
        Move a personal document to an active person or trash it.
        ---
        Mueve el documento de persona a su ficha (activa o dueño) o lo
        manda a la papelera, según la regla de Miguel Ángel.
        """
        person, how = resolve_person(full, entry.name)
        is_active = bool(person) and (
            person.is_active_employee or person.pk in owner_pks
        )
        if not is_active:
            reason = (
                "persona %s (pk=%d) NO activa [%s]" % (
                    person, person.pk, how,
                ) if person else how
            )
            person_trash.append((entry, code, reason))
            if apply_changes:
                DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                    deleted_at=timezone.now(),
                )
            return

        expiry = None
        if code == "DNI":
            expiry = extract_dni_mrz_expiry(full) or \
                extract_dni_front_expiry(full)
        latest = DocumentIndexEntry.objects.filter(
            domain_content_type=person_ct, domain_object_id=person.pk,
            document_type__code=code, deleted_at__isnull=True,
            purged_at__isnull=True, expiry_date__isnull=False,
        ).order_by("-expiry_date").values_list(
            "expiry_date", flat=True,
        ).first()
        if expiry and (latest is None or expiry > latest):
            vigencia = (
                "VIGENTE (caduca %s; el mas reciente de la ficha: %s)"
                % (expiry, latest or "ninguno")
            )
        elif expiry:
            vigencia = "HISTORICO (caduca %s; la ficha ya tiene %s)" % (
                expiry, latest,
            )
        else:
            vigencia = "sin caducidad legible"
        person_moves.append((entry, code, person, how, vigencia))
        if apply_changes and code in catalog:
            fields = {
                "document_type": catalog[code],
                "domain_content_type": person_ct,
                "domain_object_id": person.pk,
            }
            if expiry:
                fields["expiry_date"] = expiry
            DocumentIndexEntry.objects.filter(pk=entry.pk).update(**fields)

    def _summary(self, apply_changes, total, by_type, person_moves,
                 person_trash, unresolved):
        """
        Final report: types with real examples, persons, unresolved.
        ---
        Resumen final: tipos con ejemplos reales, personas y pendientes.
        """
        self._log_plain("=== RESUMEN PASO B (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    documentos revisados: %d" % total)
        self._log_plain("    tipados: %d" % sum(
            len(v) for v in by_type.values()
        ))
        self._log_plain("    personas -> a su ficha: %d" % len(person_moves))
        self._log_plain("    personas -> papelera: %d" % len(person_trash))
        self._log_plain("    sin resolver: %d" % len(unresolved))
        self._log_plain("--- POR TIPO (todos, con inicio de cabecera) ---")
        for code, items in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
            self._log_plain("  %s: %d" % (code, len(items)))
            for entry, header in items:
                self._log_plain("      id=%d %s | %s" % (
                    entry.id, entry.name, header[:110],
                ))
        self._log_plain("--- PERSONAS A SU FICHA ---")
        for entry, code, person, how, vigencia in person_moves:
            self._log_plain("    id=%d %s -> %s de %s (pk=%d) [%s] %s" % (
                entry.id, entry.name, code, person, person.pk, how, vigencia,
            ))
        self._log_plain("--- PERSONAS A LA PAPELERA ---")
        for entry, code, reason in person_trash:
            self._log_plain("    id=%d %s (%s) -- %s" % (
                entry.id, entry.name, code, reason,
            ))
        self._log_plain("--- SIN RESOLVER (todos, con inicio del texto) ---")
        for entry, reason in unresolved:
            self._log_plain("    id=%d %s -- %s | %s" % (
                entry.id, entry.name, reason,
                normalize(entry.ocr_text)[:140],
            ))
