# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/scan_essential_documents.py
"""
H30 (S127). Essential documents of active people with notices, page by
page, on the stored full OCR text. No Gemini.

---

H30 (S127). Miguel Ángel: centrarse en las personas ACTIVAS con avisos,
mirar sus documentos esenciales (contratos y altas, DNI/NIE, permiso de
conducción, CAP, tarjeta de conductor, carnet de gruista...) y sacar a
la luz lo que esté escondido -- sin gastar en Gemini (el OCR completo ya
está pagado y guardado) y con cuidado con los dossieres.

Por cada página del OCR (`FULL_OCR_MARKER`, "=== Página N ===") de cada
archivo de la persona (`candidate_files`: vinculados, su carpeta,
carpetas antiguas con su nombre, papelera):
- Qué documentos esenciales hay (marcas impresas: "DOCUMENTO NACIONAL DE
  IDENTIDAD", IDESP, "PERMISO DE CONDUCCIÓN", "CUALIFICACIÓN DEL
  CONDUCTOR"...). Una página puede tener varios.
- Si es de ESTA persona: su número de documento completo, o primer
  apellido y nombre, en ESA página (un dossier de cuadrilla trae a
  otros; esas páginas no se le atribuyen).
- Las fechas impresas en la página.
Y se compara con la BD: archivos vivos de la persona con el tipo de ese
documento y su fecha. Un hallazgo dentro de un archivo de OTRO tipo, en
la papelera o fuera de su ficha sale como POSIBLE ESCONDIDO -- para
revisar a ojo, nunca para corregir sin más.

Solo lectura. Log propio con --log-file (com-standards 0bis).
"""
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from document_explorer import document_notice_service as notices
from document_explorer.cloud_vision_service import FULL_OCR_MARKER
from document_explorer.document_audit_service import (
    _pages_of, candidate_files,
)
from document_explorer.employment_period_service import CONTRACT_COVER_CODES
from document_explorer.models import DocumentIndexEntry, PersonIdentity

# Documento esencial -> (marcas impresas, tipos de la BD que lo cubren).
ESSENTIAL = {
    "DNI": (
        ("DOCUMENTO NACIONAL DE IDENTIDAD", "NATIONAL IDENTITY CARD",
         "IDESP"),
        ("DNI",),
    ),
    "NIE / PERMISO DE RESIDENCIA": (
        ("PERMISO DE RESIDENCIA", "RESIDENCE PERMIT",
         "TARJETA DE IDENTIDAD DE EXTRANJERO",
         "CERTIFICADO DE REGISTRO DE CIUDADANO"),
        ("NIE",),
    ),
    "PERMISO DE CONDUCCION": (
        ("PERMISO DE CONDUCCION", "DRIVING LICENCE"),
        ("CARNET_CONDUCIR",),
    ),
    "CAP": (
        ("CUALIFICACION DEL CONDUCTOR", "CUALIFICACION DE CONDUCTOR"),
        ("TARJETA_CUALIF_CONDUCTOR",),
    ),
    "TARJETA DE CONDUCTOR (TACOGRAFO)": (
        ("TARJETA DE CONDUCTOR", "DRIVER CARD"),
        ("TACOGRAFO",),
    ),
    "CARNET DE GRUISTA": (
        ("OPERADOR DE GRUA", "OPERADORES DE GRUAS",
         "GRUA MOVIL AUTOPROPULSADA"),
        ("CARNET_GRUISTA",),
    ),
    "CONTRATO": (
        ("CONTRATO DE TRABAJO", "CONVERSION DE CONTRATO",
         "SUBROGACION", "COMUNICACION DEL CONTRATO"),
        tuple(CONTRACT_COVER_CODES),
    ),
    "ALTA EN LA SEGURIDAD SOCIAL": (
        ("RECONOCIMIENTO DE ALTA", "SITUACION DE ALTA",
         "ALTA, BAJA O VARIACION"),
        ("ALTA",),
    ),
}
_DATE_RE = re.compile(r"\b(\d{2})[ /.-](\d{2})[ /.-](\d{4})\b")


def _plain(text):
    """Upper case, no accents, single spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.upper())


def _belongs(person, plain_page):
    number = re.sub(r"[^0-9A-Z]", "", (person.dni or "").upper())
    if len(number) >= 9 and number in re.sub(r"[^0-9A-Z]", "", plain_page):
        return "nº %s" % person.dni
    surname = _plain(person.first_surname).strip()
    given = _plain(person.given_name).split()
    if surname and given and surname in plain_page and given[0] in plain_page:
        return "nombre"
    return None


class Command(BaseCommand):
    help = (
        "S127: documentos esenciales de los activos con avisos, página a "
        "página sobre el OCR guardado. Solo lectura, sin Gemini."
    )

    def add_arguments(self, parser):
        parser.add_argument("--log-file", required=True)
        parser.add_argument("--person", type=int, action="append")

    def _say(self, text):
        self.stdout.write(text)
        self.stdout.flush()
        self._log.write(text + "\n")
        self._log.flush()

    def handle(self, *args, **options):
        self._log = open(options["log_file"], "a", encoding="utf-8")
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        if options["person"]:
            people = list(PersonIdentity.objects.filter(
                pk__in=options["person"]))
        else:
            pending, _scheduled, _calendar = notices.compute_notices(
                notices.DOMAIN_PERSONAL,
            )
            pks = {
                int(n.notice_key.split("|")[1]) for n in pending
                if n.kind in (notices.KIND_MISSING, notices.KIND_EXPIRED)
            }
            people = list(PersonIdentity.objects.filter(
                pk__in=pks, is_active_employee=True,
            ).order_by("first_surname", "given_name"))
        self._say("# [ESENCIALES] %d persona(s) activa(s) con avisos." %
                  len(people))
        for number, person in enumerate(people, 1):
            close_old_connections()
            files = candidate_files(person)
            self._say("\n== [%d/%d] pk=%s %s %s, %s (doc %s) -- %d archivo(s)"
                      % (number, len(people), person.pk, person.first_surname,
                         person.second_surname or "", person.given_name,
                         person.dni, len(files)))
            no_ocr = [
                entry for entry in files
                if not (entry.ocr_text or "").startswith(FULL_OCR_MARKER)
            ]
            if no_ocr:
                self._say("   sin OCR completo: %d archivo(s) -- %s" % (
                    len(no_ocr), ", ".join(
                        "pk=%s %s" % (e.pk, e.name) for e in no_ocr[:8])))
            for label, (marks, codes) in ESSENTIAL.items():
                in_db = list(DocumentIndexEntry.objects.filter(
                    domain_content_type=person_ct, domain_object_id=person.pk,
                    document_type__code__in=codes,
                    deleted_at__isnull=True, purged_at__isnull=True,
                ).order_by("-expiry_date", "-issue_date"))
                hits = []
                for entry in files:
                    text = entry.ocr_text or ""
                    if not text.startswith(FULL_OCR_MARKER):
                        continue
                    for page, page_text in _pages_of(text):
                        plain = _plain(page_text)
                        if not any(mark in plain for mark in marks):
                            continue
                        who = _belongs(person, plain)
                        if who is None:
                            continue
                        dates = sorted({
                            "%s/%s/%s" % m.groups()
                            for m in _DATE_RE.finditer(plain)
                        })
                        hits.append((entry, page, who, dates))
                if not in_db and not hits:
                    continue
                self._say("  -- %s: en BD %d archivo(s)%s" % (
                    label, len(in_db),
                    " (el más reciente: pk=%s %s, cad. %s, fecha %s)" % (
                        in_db[0].pk, in_db[0].name, in_db[0].expiry_date,
                        in_db[0].issue_date) if in_db else ""))
                db_pks = {entry.pk for entry in in_db}
                in_db_hits = [h for h in hits if h[0].pk in db_pks]
                if in_db_hits:
                    self._say("     (%d página(s) en archivos ya tipados como "
                              "este documento)" % len(in_db_hits))
                for entry, page, who, dates in hits:
                    if entry.pk in db_pks:
                        continue
                    code = (entry.document_type.code
                            if entry.document_type else "sin tipo")
                    status = "POSIBLE ESCONDIDO (archivo tipo %s%s%s)" % (
                        code,
                        ", PAPELERA" if entry.deleted_at else "",
                        "" if entry.domain_object_id == person.pk
                        else ", no vinculado a la persona")
                    self._say("     pk=%s pág.%s [%s] %s | por %s | fechas %s"
                              % (entry.pk, page, status, entry.name, who,
                                 ", ".join(dates[:6]) or "-"))
        self._say("\n# [ESENCIALES] Fin.")
