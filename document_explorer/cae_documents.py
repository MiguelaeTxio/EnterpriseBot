# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/cae_documents.py
"""
Typing of the CAE company documentation by folder and file name (S156).

The H28 agent uploads the monthly company documentation that the CAE
platforms ask for ("00 DOCUMENTACION MENSUAL 2026" in OneDrive), and
consume_quarantine_task moves it to buckets.CAE_ROOT keeping its
OneDrive path. Those folders and names follow a fixed convention, so
each file is typed by rules, never by Gemini: document type from the
folder (and a keyword of the name), group company from the path, and
date from the name or, failing that, from the month folder.

---

Tipado de la documentacion CAE de las empresas por carpeta y nombre
(S156). La documentacion mensual que piden las plataformas de
coordinacion (egestiona, Cellnex, Nalanda, Quioo) llega a
buckets.CAE_ROOT con su ruta de OneDrive, y sus carpetas y nombres
siguen siempre la misma convencion: tipo por carpeta (y una palabra
del nombre), empresa del grupo por la ruta y fecha por el nombre o,
si no la trae, por la carpeta del mes. Sin Gemini. Lo que no encaja
en ninguna regla (facturas del servicio de prevencion, partes de
accidente, certificados de haberes de cada trabajador...) se queda
sin tipo, en su carpeta.
"""
import datetime
import logging
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType

from document_explorer.buckets import CAE_ROOT
from document_explorer.models import (
    CompanyFiscalProfile,
    DocumentTypeCatalog,
)

logger = logging.getLogger(__name__)

# CIF de las 4 empresas del grupo (CompanyFiscalProfile, S113).
_TAX_GRUAS_ALVAREZ = "B29405040"
_TAX_TRANSGRUAL = "B92493022"
_TAX_GRANADA = "B93261824"
_TAX_GRUALDI = "B29739059"

# Nombre corto de cada empresa en el nombre canónico (S156).
_COMPANY_TOKENS = {
    _TAX_GRUAS_ALVAREZ: "GRUAS_ALVAREZ",
    _TAX_TRANSGRUAL: "TRANSGRUAL",
    _TAX_GRANADA: "GRUAS_GRANADA",
    _TAX_GRUALDI: "GRUALDI",
}
# Tipos que conservan su nombre de OneDrive: el certificado nominativo
# de Hacienda es para un contratista concreto que solo dice el nombre.
_KEEP_NAME_CODES = ("CERT_CONTRATISTAS_AEAT",)

_MONTHS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "JULIIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

# dd-mm-aaaa, dd-mm-aa, d.m.aa, dd/mm/aaaa.
_DATE_RE = re.compile(r"\b(\d{1,2})[-./](\d{1,2})[-./](\d{4}|\d{2})\b")
# "2026 09 TC1 ..." (periodo de cotizacion al principio del nombre).
_PERIOD_RE = re.compile(r"^(20\d{2})\s+(\d{2})\b")
# "TC2 TRANSGRUAL 05-2026", "09 -2026".
_MONTH_YEAR_RE = re.compile(r"\b(\d{1,2})\s*-\s*(20\d{2})\b")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
# Transgrual abreviada ("IAE TR ...", "IAE TRA 2026") o con errata.
_TRANSGRUAL_RE = re.compile(r"\bTRA?\b|TRNASGRUAL|\(TR\)")


def _plain(text):
    """Upper case without accents.
    ---
    Mayusculas y sin tildes.
    """
    text = unicodedata.normalize("NFKD", (text or "").replace("_", " "))
    return "".join(
        char for char in text if not unicodedata.combining(char)
    ).upper()


def _company_tax_id(text):
    """Group company of a CAE file from its path and name, or None.
    ---
    Empresa del grupo de un archivo CAE por su ruta y nombre, o None.
    Granada y Grualdi van primero (sus nombres contienen "GRUAS"); el
    autonomo Adolfo Alvarez Diaz no es ninguna de las 4 empresas.
    """
    if "GRANADA" in text:
        return _TAX_GRANADA
    if "GRUALDI" in text:
        return _TAX_GRUALDI
    if "TRANSGRUAL" in text or _TRANSGRUAL_RE.search(text):
        return _TAX_TRANSGRUAL
    if (
        "GRUAS ALVAREZ" in text or "GRUAS ADOLFO ALVAREZ" in text
        or "GRUAS A.ALVAREZ" in text or "(GR)" in text
    ):
        return _TAX_GRUAS_ALVAREZ
    return None


def _type_code(section, rest, name):
    """Catalogue code for a CAE file, or None when no rule fits.
    ---
    Codigo del catalogo de un archivo CAE, o None si no encaja ninguna
    regla. `section` es la carpeta de primer nivel dentro de la
    documentacion mensual; `rest`, el resto de la ruta; `name`, el
    nombre del archivo (todo en mayusculas y sin tildes).
    """
    if section == "TCS Y RECIBOS":
        if "TC1" in name:
            return "TC1_EMPRESA"
        if "TC2" in name:
            return "TC2_EMPRESA"
        if "VIDA LABORAL" in name:
            return "VIDA_LABORAL_EMPRESA"
        if "RECIBO" in name:
            return "RECIBO_LIQUIDACION_SS"
        return None
    if section == "CERTIFICADOS TGSS":
        if "ART.42" in name or "ART 42" in name:
            return "CERT_ART42_TGSS"
        if "RESOLUCION" in name or "DEUDA" in name:
            return None
        return "CERT_CORRIENTE_SS_EMPRESA"
    if section == "CERTIFICADO AEAT NOMINATIVOS":
        if "ESTAR AL CORRIENTE" in name:
            return "CERT_CORRIENTE_AEAT"
        return "CERT_CONTRATISTAS_AEAT"
    if section == "ITAS":
        return "ITA_EMPRESA"
    if section == "2026 PRL ERL PAP CERTIFICADOS MPE" or (
        "PRL" in section and "MPE" in section
    ):
        if "ERL" in rest:
            return "EVALUACION_RIESGOS_EMPRESA"
        if "PAP" in rest:
            return "PLANIFICACION_PREVENTIVA"
        if "PLAN PREVENCION" in rest:
            return "PLAN_PREVENCION"
        if "EMERGENCIA" in rest:
            return "MEDIDAS_EMERGENCIA"
        if "PROCEDIMIENTO" in rest:
            return "PROCEDIMIENTOS_TRABAJO"
        if "CERTIFICADO SPA" in name:
            return "CERT_SERVICIO_PREVENCION"
        return None
    if section == "REA REGISTRO DE EMPRESAS ACREDITADAS":
        if "RENOVACION" in rest:
            return None
        return "CERT_REA"
    if section == "IAE":
        return "RECIBO_IAE"
    if section == "FRATERNIDAD MUPRESPA":
        if "ASOCIACION" in name:
            return "CERT_ASOCIACION_MUTUA"
        return None
    if section == "CERTIFICADOS HABERES PAGOS NOMINAS":
        if (
            "CORRIENTE PAGO" in name or "CERTIFICADO SALARIOS" in name
            or "CERTIFICADO PAGOS" in name
        ):
            return "PAGO_CORRIENTE"
        return None
    return None


def _file_date(name, folders):
    """Date of a CAE file from its name, else from its month folder.
    ---
    Fecha de un archivo CAE por su nombre (dd-mm-aaaa, "2026 09 TC1",
    "05-2026") o, si no la trae, el dia 1 del mes (carpeta o nombre)
    con el ano de la ruta; con solo el ano, el 1 de enero. None si no
    hay forma de saberla.
    """
    match = _DATE_RE.search(name)
    if match:
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass
    match = _PERIOD_RE.match(name)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), 1)
        except ValueError:
            pass
    match = _MONTH_YEAR_RE.search(name)
    if match and 1 <= int(match.group(1)) <= 12:
        return datetime.date(int(match.group(2)), int(match.group(1)), 1)
    year = None
    month = None
    for text in folders + [name]:
        found = _YEAR_RE.search(text)
        if found and text is not name:
            year = int(found.group(1))
        for word in re.split(r"[^A-Z]+", text):
            if word in _MONTHS:
                month = _MONTHS[word]
    name_year = _YEAR_RE.search(name)
    if name_year and (year is None or month is None):
        year = int(name_year.group(1))
        if month is None:
            month = 1
    if year and month:
        return datetime.date(year, month, 1)
    return None


def type_cae_entry(entry):
    """Type one CAE file in place (type, company, date). True if typed.
    ---
    Tipa un archivo CAE (tipo, empresa del grupo y fecha) sin moverlo.
    Una fecha futura es la de validez del certificado ("VALIDO
    31-12-27", "CERTIFICADO SPA 05-02-27") y va a expiry_date; las
    demas, a issue_date. Devuelve True si le ha puesto tipo.
    """
    prefix = CAE_ROOT + "/"
    if not entry.parent_path.startswith(prefix):
        return False
    folders = [
        _plain(part) for part in entry.parent_path[len(prefix):].split("/")
    ]
    # [0] = "00 DOCUMENTACION MENSUAL 2026" / "00 OBRAS EN EJECUCION 2026".
    if len(folders) < 2 or "DOCUMENTACION MENSUAL" not in folders[0]:
        return False
    section = folders[1]
    rest = " / ".join(folders[2:])
    name = _plain(entry.name)

    code = _type_code(section, rest, name)
    if code is None:
        return False
    document_type = DocumentTypeCatalog.objects.filter(code=code).first()
    if document_type is None:
        logger.warning("CAE: tipo %s no existe en el catalogo.", code)
        return False

    fields = ["document_type"]
    entry.document_type = document_type

    tax_id = _company_tax_id(" / ".join(folders[1:] + [name]))
    company = (
        CompanyFiscalProfile.objects.filter(tax_id=tax_id).first()
        if tax_id else None
    )
    if company is not None:
        entry.domain_content_type = ContentType.objects.get_for_model(
            CompanyFiscalProfile)
        entry.domain_object_id = company.pk
        fields += ["domain_content_type", "domain_object_id"]

    found = _file_date(name, folders)
    if found is not None:
        if found > datetime.date.today():
            entry.expiry_date = found
            fields.append("expiry_date")
        else:
            entry.issue_date = found
            fields.append("issue_date")

    entry.save(update_fields=fields)
    rename_cae_entry(entry)
    return True


def canonical_name(entry):
    """Canonical name for a typed CAE file, or None to keep its name.
    ---
    Nombre canónico de un archivo CAE ya tipado:
    {EMPRESA}_{TIPO}_{FECHA}[_N] (sin empresa, {TIPO}_{FECHA}). None
    si no tiene tipo o es de los que conservan su nombre (nominativos
    de Hacienda). La fecha es la de validez si la hay; si no, la del
    documento. Una colisión en la carpeta lleva ordinal.
    """
    from document_explorer import naming_service
    from document_explorer.move_service import _virtual_location_taken

    if entry.document_type_id is None:
        return None
    code = entry.document_type.code
    if code in _KEEP_NAME_CODES:
        return None
    company = None
    if entry.domain_object_id and entry.domain_content_type_id == (
            ContentType.objects.get_for_model(CompanyFiscalProfile).pk):
        company = CompanyFiscalProfile.objects.filter(
            pk=entry.domain_object_id).first()
    token = _COMPANY_TOKENS.get(company.tax_id) if company else None
    date = entry.expiry_date or entry.issue_date
    extension = entry.name.rsplit(".", 1)[-1] if "." in entry.name else "pdf"

    def build(ordinal=None):
        if token:
            return naming_service.build_filename_group_company(
                token, code, date, ordinal=ordinal, extension=extension)
        return naming_service.build_filename_company(
            code, date, ordinal=ordinal, extension=extension)

    name = build()
    ordinal = 1
    while _virtual_location_taken(
            entry.bucket, entry.parent_path, name, exclude_pk=entry.pk):
        name = build(ordinal)
        ordinal += 1
    return name


def rename_cae_entry(entry):
    """Give a typed CAE file its canonical name. True if renamed.
    ---
    Pone a un archivo CAE tipado su nombre canónico (solo el nombre
    virtual del índice; el objeto de GCS no se toca). True si cambió.
    """
    name = canonical_name(entry)
    if not name or name == entry.name:
        return False
    entry.name = name
    entry.save(update_fields=["name"])
    return True
