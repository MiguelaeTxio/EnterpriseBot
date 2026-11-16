# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/builder.py
"""
Builds the data of an insurance renewal report from the document
readings and the ledger entries.

---

Monta los datos de un informe de renovación de seguros, lo mismo que se
hizo a mano en S152 para Alejandro:

1. Cada documento leído (recibo, póliza, certificado) se agrupa en su
   seguro: por máquina, tipo y aseguradora, o por número de póliza en los
   de empresa. Del grupo vale el documento más reciente; el del año
   anterior da la prima anterior.
2. Los apuntes de los libros mayores marcados se casan con cada seguro
   por matrícula, número de póliza o centro de gasto. Lo que se ha
   pagado manda: el mayor da la prima anual (suma de los recibos de 12
   meses), hasta cuándo está pagado y la aseguradora real.
3. Lo que solo está en el mayor entra como seguro más («no estaba en
   los documentos»), con el tipo que decide Gemini.
4. Avisos: vencido o sin renovar, doble seguro, aseguradora distinta,
   precio distinto entre documento y mayor, vehículo de baja asegurado,
   sin precio, sin recibo en el mayor.
5. Las flotas (cinco o más vehículos de la misma póliza) salen en una
   línea con el detalle de sus vehículos.
6. Solo quedan los seguros que vencen entre los meses pedidos (los ya
   vencidos desde el mes de inicio también, para verlos).
"""
import collections
import datetime
import re

from django.contrib.contenttypes.models import ContentType

from fleet.models import MachineAsset
from insurance import companies
from insurance.models import InsuranceDocumentReading
from insurance.readings import CATEGORY_LABELS
from insurance.readings import CATEGORIES

ORDER = [key for key, _label in CATEGORIES]
_PLATE = re.compile(r"\d{4}[A-Z]{1,3}")
_BRANDS = (
    ("CHUBB", "Chubb"), ("AXA", "AXA"), ("ARAG", "ARAG"),
    ("ALLIANZ", "Allianz"), ("HELVETIA", "Helvetia"),
    ("MAPFRE", "Mapfre"), ("EUROP", "Europ Assistance"),
    ("ZURICH", "Zurich"), ("OCCIDENT", "Occident"),
    ("SEGUROS GENERALES RURAL", "Caja Rural"),
    ("CAJAMAR VIDA", "Cajamar Vida"), ("CAJAMAR", "Cajamar"),
    ("ASEFA", "ASEFA"), ("CASER", "Caser"), ("SANTANDER", "Santander"),
    ("ABANCA", "Abanca"), ("CESCE", "CESCE"),
    ("SEGUROS REUNIDOS", "Caser"),
    ("LAGE LANDEN", "De Lage Landen"),
    ("SANITAS", "Sanitas"), ("ADESLAS", "Adeslas"),
    ("SEGURCAIXA", "Adeslas"), ("ADELAS", "Adeslas"), ("REALE", "Reale"),
    ("LIBERTY", "Liberty"),
    ("PLUS ULTRA", "Plus Ultra"), ("CATALANA", "Catalana Occidente"),
    ("MUTUA MADRILENA", "Mutua Madrileña"), ("GENERAL", "Generali"),
)
_BROKERS = (
    ("ALKORA", "Alkora"), ("MEDITRES", "Meditres"), ("ASADA", "Asada"),
    ("GALVEZ", "Gálvez Trinidad"), ("SEYVER", "Seyver"),
    ("CONSULTORES DEL SEGURO", "Seyver"), ("AICO", "AICO Mediación"),
)
FLEET_MIN_VEHICLES = 5
PRICE_TOLERANCE = 1.0


def brand(text):
    """
    Insurer brand of a free text ("" if none).
    ---
    Marca de la aseguradora de un texto libre («GENERALLI ESPAÑA (VITAL/
    ESTREL)» -> Generali). Las marcas largas van antes que las cortas
    para que «AXA SEGUROS GENERALES» sea AXA.
    """
    value = companies.plain(text).replace(" ", "")
    if not value:
        return ""
    if value == "ALLI":
        # Recibo con la aseguradora cortada (S152, B46).
        return "Allianz"
    for key, name in _BRANDS:
        if key.replace(" ", "") in value:
            return name
    return str(text).strip().title()[:40]


def broker(text):
    """
    Broker short name of a free text ("" if none).
    ---
    Nombre corto del mediador de un texto libre.
    """
    value = companies.plain(text)
    if not value or "CONSTA" in value:
        return ""
    for key, name in _BROKERS:
        if key in value:
            return name
    return str(text).strip()[:40]


def _plates(*texts):
    """
    Plate cores (4 digits + letters) found in the texts.
    ---
    Núcleos de matrícula (4 cifras y letras) de los textos, sin la letra
    de provincia ni la E/R de los especiales: «E-4598-BCJ» -> 4598BCJ.
    """
    found = set()
    for text in texts:
        value = re.sub(r"[^A-Z0-9]", "", companies.plain(text))
        found.update(_PLATE.findall(value))
    return found


def _digits(text):
    return re.sub(r"\D", "", str(text or ""))


def _zdigits(text):
    return _digits(text).replace("0", "")


def _date(text):
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def _letters_typo(a, b):
    """
    Same plate except one letter (or two swapped letters).
    ---
    Misma matrícula salvo una letra cambiada o dos letras traspuestas:
    las erratas típicas del concepto del mayor (FCX por FCZ, MGL por
    MLG). Nunca si cambia una cifra (2030JVK y 2034JVK son dos coches).
    """
    if len(a) != len(b) or a[:4] != b[:4] or a == b:
        return a == b
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diff) == 1:
        return True
    return (len(diff) == 2 and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])


def _cost_centre(code):
    match = re.match(r"^([A-Z])-?0*(\d{1,3})$", (code or "").upper())
    return "%s%02d" % (match.group(1), int(match.group(2))) if match else ""


ANNUAL_FACTOR = {"semestral": 2, "trimestral": 4, "mensual": 12,
                 "bimestral": 6, "cuatrimestral": 3}


# ----------------------------------------------------------------------
# 1. Documentos -> seguros
# ----------------------------------------------------------------------

def _doc_items(entries):
    """
    One dict per read document with the fields the report needs.
    ---
    Un dict por documento leído con lo que necesita el informe.
    """
    machine_ct = ContentType.objects.get_for_model(MachineAsset)
    readings = {
        r.entry_id: r.data for r in InsuranceDocumentReading.objects.filter(
            entry_id__in=[e.pk for e in entries], data__isnull=False)
    }
    machine_ids = {e.domain_object_id for e in entries
                   if e.domain_content_type_id == machine_ct.pk}
    machines = {m.pk: m for m in MachineAsset.objects.filter(
        pk__in=machine_ids)}
    items = []
    for entry in entries:
        data = readings.get(entry.pk)
        if not data or data.get("document_kind") in (
                "carta_verde", "condiciones_generales", "no_es_seguro"):
            continue
        machine = (machines.get(entry.domain_object_id)
                   if entry.domain_content_type_id == machine_ct.pk
                   else None)
        company = ""
        if machine is not None:
            company = companies.detect(machine.company_name,
                                       machine.company_code)
        company = company or companies.detect(
            data.get("policyholder"), entry.parent_path)
        frequency = companies.plain(
            data.get("payment_frequency")).lower()
        premium = data.get("total_premium")
        annual = premium
        if premium and data.get("document_kind") == "recibo":
            for word, factor in ANNUAL_FACTOR.items():
                if word in frequency:
                    annual = round(premium * factor, 2)
        items.append({
            "entry_id": entry.pk,
            "name": entry.name,
            "kind": data.get("document_kind"),
            "category": data.get("category") or "otros",
            "machine": machine,
            "company": company,
            "insurer": brand(data.get("insurer")),
            "broker": broker(data.get("broker")),
            "policy": (data.get("policy_number") or "").strip(),
            "plates": _plates(*(data.get("insured_plates") or []),
                              machine.plate if machine else ""),
            "object": (data.get("insured_object") or "").strip(),
            "cover": (data.get("cover") or "").strip(),
            "premium": premium,
            "annual": annual,
            "frequency": (data.get("payment_frequency") or "").strip(),
            "period_end": _date(data.get("period_end")),
            "due": (_date(data.get("renewal_date"))
                    or _date(data.get("period_end")) or entry.expiry_date),
            "notes": (data.get("notes") or "").strip(),
        })
    return items


# S152: Caser es de Helvetia y sus pólizas (C6 A96 …) salen leídas con
# una u otra marca según el documento.
_SAME_GROUP = {"Caser": "Helvetia"}


def _insurer_group(insurer):
    return _SAME_GROUP.get(insurer, insurer)


def _known(insurer):
    return insurer not in ("", "No consta")


def _fill_insurers(records):
    """
    Take the insurer of a record from another one with its policy.
    ---
    Un seguro con la aseguradora sin leer toma la de otro con el mismo
    número de póliza (S152: 3233NJM «No consta» con la póliza de flota
    24G427000388 de Generali).
    """
    by_policy = {}
    for record in records:
        number = _digits(record["policy"])
        if len(number) >= 5 and _known(record["insurer"]):
            by_policy.setdefault(number, record["insurer"])
    for record in records:
        number = _digits(record["policy"])
        if not _known(record["insurer"]) and number in by_policy:
            record["insurer"] = by_policy[number]


def _machine_pk(item):
    return item["machine"].pk if item["machine"] is not None else None


def _same_content(a, b):
    """
    Two readings of the same document (same receipt, other file).
    ---
    Dos lecturas del mismo documento en archivos distintos: un recibo
    protegido y su copia ya sin protección tienen otro hash pero el
    mismo contenido (Miguel Ángel, S152: salían como seguros
    duplicados). Mismo tipo, mismo vehículo (máquina o matrícula),
    vencimiento a menos de un mes y la misma prima, o, sin prima en
    ninguno, el mismo número de póliza.
    """
    if a["kind"] != b["kind"] or not a["due"] or not b["due"]:
        return False
    if abs((a["due"] - b["due"]).days) > 31:
        return False
    if _machine_pk(a) is not None and _machine_pk(b) is not None:
        # La misma póliza de flota guardada en la carpeta de cada
        # máquina no es un duplicado: cada máquina lleva la suya.
        same_unit = _machine_pk(a) == _machine_pk(b)
    else:
        same_unit = bool(a["plates"] & b["plates"])
    if not same_unit:
        return False
    if a["premium"] is not None and b["premium"] is not None:
        return abs(a["premium"] - b["premium"]) < 0.01
    if a["premium"] is None and b["premium"] is None:
        pa, pb = _digits(a["policy"]), _digits(b["policy"])
        return len(pa) >= 5 and len(pb) >= 5 and (pa in pb or pb in pa)
    return False


def _completeness(item):
    return (item["insurer"] not in ("", "No consta"),
            bool(item["broker"]), bool(item["frequency"]),
            len(item["policy"]))


def _dedupe(items):
    """
    Keep one item per document content.
    ---
    Deja un solo documento por contenido (ver _same_content): se queda
    el más completo y toma del otro lo que le falte.
    """
    kept = []
    for item in sorted(items, key=_completeness, reverse=True):
        twin = next((k for k in kept if _same_content(k, item)), None)
        if twin is None:
            kept.append(item)
            continue
        for field in ("broker", "frequency", "policy", "cover"):
            if not twin[field] and item[field]:
                twin[field] = item[field]
        twin.setdefault("twins", []).append(item["entry_id"])
    return kept


def _group_key(item):
    machine = item["machine"]
    policy = re.sub(r"[^A-Z0-9]", "", companies.plain(item["policy"]))
    if machine is not None:
        return ("M", machine.pk, item["category"], item["insurer"])
    if len(policy) >= 5:
        return ("P", item["company"], policy)
    plates = sorted(item["plates"])
    if plates:
        return ("V", plates[0], item["category"], item["insurer"])
    return ("O", item["company"], item["insurer"], item["category"],
            companies.plain(item["object"])[:40])


def _records_from_docs(items):
    """
    Group the documents into insurances (one record each).
    ---
    Agrupa los documentos en seguros: del grupo vale el más reciente
    (por vencimiento) y, si ese no trae prima, la del recibo del mismo
    periodo; la prima del año anterior sale del documento que vence
    entre 10 y 14 meses antes.
    """
    groups = collections.defaultdict(list)
    for item in _dedupe(items):
        groups[_group_key(item)].append(item)
    records = []
    for docs in groups.values():
        docs.sort(key=lambda d: (d["due"] or datetime.date.min,
                                 d["premium"] is not None))
        last = docs[-1]
        due = last["due"]
        priced = [d for d in docs if d["annual"] and d["due"] and due
                  and abs((d["due"] - due).days) <= 45]
        current = priced[-1] if priced else last
        previous = None
        if due:
            older = [d for d in docs if d["annual"] and d["due"]
                     and 300 <= (due - d["due"]).days <= 430]
            previous = older[-1] if older else None
        machine = last["machine"]
        records.append({
            "category": last["category"],
            "company": last["company"],
            "machine_id": machine.pk if machine else None,
            "machine_active": machine.is_active if machine else None,
            "cost_centre": _cost_centre(machine.code) if machine else "",
            "code": machine.code if machine else "",
            "plate": (machine.plate if machine else "") or ", ".join(
                sorted(last["plates"])),
            "plates": set().union(*(d["plates"] for d in docs)),
            "object": _object_text(machine, last),
            "insurer": last["insurer"],
            "insurer_doc": last["insurer"],
            "broker": next((d["broker"] for d in reversed(docs)
                            if d["broker"]), ""),
            "policy": next((d["policy"] for d in reversed(docs)
                            if d["policy"]), ""),
            "cover": last["cover"],
            "due": due,
            "premium": current["annual"],
            "premium_source": "Documento" if current["annual"] else "",
            "receipt": current["premium"],
            "frequency": current["frequency"] or last["frequency"],
            "previous": previous["annual"] if previous else None,
            "notes": last["notes"],
            "documents": [d["entry_id"] for d in docs],
            "origin": "Documento",
            "ledger": [],
            "alerts": [],
            "comments": [],
        })
    return records


def _object_text(machine, item):
    if machine is not None:
        parts = [machine.code, machine.plate or "",
                 machine.brand_model or machine.type_name or ""]
        return " · ".join(p for p in parts if p)
    return item["object"] or item["cover"] or "Seguro"


# ----------------------------------------------------------------------
# 2. Libro mayor
# ----------------------------------------------------------------------

def ledger_entries(ledgers):
    """
    The ledger lines of the chosen ledgers, without repeats.
    ---
    Los apuntes de los libros mayores marcados, sin repetir los que
    salen en dos listados que se solapan.
    """
    seen, result = set(), []
    for ledger in ledgers:
        for entry in ledger.entries or []:
            key = (ledger.company_code, entry["project"], entry["account"],
                   entry["date"], entry["concept"], entry["amount"])
            if key in seen:
                continue
            seen.add(key)
            item = dict(entry)
            item["company"] = ledger.company_code
            item["brand"] = brand(entry["insurer_text"])
            item["concept_plain"] = re.sub(
                r"[^A-Z0-9]", "", companies.plain(entry["concept"]))
            item["plates"] = set(_PLATE.findall(item["concept_plain"]))
            item["numbers"] = re.findall(r"\d{5,}", item["concept_plain"])
            item["project_plates"] = _plates(entry["project_text"])
            item["i"] = len(result)
            result.append(item)
    return result


def _policy_hit(policy, entry):
    zp = _zdigits(policy)
    if len(zp) < 5:
        return False
    for number in entry["numbers"]:
        zn = number.replace("0", "")
        if zp in zn or (len(zn) >= 5 and zn in zp):
            return True
    return False


def _other_numbers(policy, entry):
    """
    Numbers in the concept that are not this policy's number.
    ---
    Números del concepto que no son el de esta póliza (otro seguro).
    """
    return [n for n in entry["numbers"]
            if not (policy and _policy_hit(policy, {"numbers": [n]}))]


def _same_unit(record, entry):
    """
    The ledger line is for this vehicle/machine (or the policy is a
    company one).
    ---
    El apunte es de este vehículo o máquina: mismo centro de gasto, o
    la matrícula en el concepto o en el proyecto. Si el seguro no es de
    ningún vehículo (póliza de empresa), vale cualquier apunte de la
    póliza; si lo es, nunca los de los demás vehículos de la flota.
    """
    cc = record["cost_centre"]
    if not cc and not record["plates"]:
        return True
    if cc and entry["cost_centre"] == cc:
        return True
    if record["plates"] & (entry["plates"] | entry["project_plates"]):
        return True
    return not entry["cost_centre"] and not entry["plates"] and not (
        entry["project_plates"])


def _match(record, entries):
    """
    The ledger lines of one insurance.
    ---
    Los apuntes de un seguro: por matrícula en el concepto (con erratas
    de letra), por número de póliza en el mismo centro de gasto, por
    centro de gasto y aseguradora cuando el concepto no nombra otra
    matrícula ni póliza, o por la matrícula del proyecto si el concepto
    no trae nada. Si no casa nada, por el importe exacto del recibo en
    la misma aseguradora y centro de gasto.
    """
    found = {}
    cc = record["cost_centre"]
    for entry in entries:
        if record["company"] and entry["company"] != record["company"] and (
                not (record["plates"] & entry["plates"])):
            continue
        why = None
        concept_plates = entry["plates"]
        if any(p in entry["concept_plain"] or any(
                _letters_typo(p, q) for q in concept_plates)
               for p in record["plates"]):
            why = "matrícula"
        elif record["policy"] and _policy_hit(record["policy"], entry) and (
                _same_unit(record, entry)):
            why = "póliza"
        elif (cc and entry["cost_centre"] == cc
              and entry["brand"] == record["insurer"]
              and not concept_plates
              and not _other_numbers(record["policy"], entry)):
            why = "centro de gasto"
        elif (record["plates"] and not concept_plates
              and not entry["numbers"]
              and record["plates"] & entry["project_plates"]):
            why = "matrícula del proyecto"
        if why:
            found[entry["i"]] = why
    same = {i: w for i, w in found.items()
            if entries[i]["brand"] == record["insurer"]
            or not record["insurer"]}
    if same:
        return same, False
    if found:
        return found, True
    if record["receipt"]:
        hits = {e["i"]: "importe" for e in entries
                if abs(e["amount"] - record["receipt"]) < 0.005
                and e["brand"] == record["insurer"]
                and (not cc or e["cost_centre"] == cc)}
        return hits, False
    return {}, False


def _ledger_summary(lines):
    """
    Paid-until date, last receipt and 12-month premium of ledger lines.
    ---
    De los apuntes de un seguro: hasta cuándo está pagado (la fecha
    «Documento» más alta), el último recibo (lo que vence ese día) y la
    prima anual (lo pagado en los 12 meses que acaban ese día).
    """
    dated = [e for e in lines if e["covered_until"]]
    until = max((_date(e["covered_until"]) for e in dated), default=None)
    last = [e for e in dated if _date(e["covered_until"]) == until]
    annual = 0.0
    for entry in lines:
        end = _date(entry["covered_until"])
        paid = _date(entry["date"])
        if until and end and end > until - datetime.timedelta(days=360):
            annual += entry["amount"]
        elif not end and until and paid and paid > (
                until - datetime.timedelta(days=365)):
            annual += entry["amount"]
        elif not until:
            annual += entry["amount"]
    return {
        "until": until,
        "last": round(sum(e["amount"] for e in last), 2),
        "annual": round(annual, 2),
        "brands": sorted({e["brand"] for e in lines}),
        "paid_at": max(_date(e["date"]) for e in lines),
        "refund": None,
    }


# ----------------------------------------------------------------------
# 3. Montaje
# ----------------------------------------------------------------------

def build(entries, ledgers, month_from, month_to=None, company_codes=(),
          today=None, classify=None):
    """
    The report data (a JSON-able dict).

    `entries`: the insurance documents (DocumentIndexEntry) already read.
    `ledgers`: InsuranceLedger objects chosen for the report.
    `classify`: function {id: text} -> {id: category} for ledger-only
    insurances (readings.classify_ledger_groups); None skips it.
    ---
    Los datos del informe (dict que se puede guardar como JSON).
    """
    today = today or datetime.date.today()
    records = _records_from_docs(_doc_items(entries))
    lines = ledger_entries(ledgers)
    ledger_companies = {}
    for ledger in ledgers:
        if ledger.date_to:
            ledger_companies[ledger.company_code] = max(
                ledger.date_to,
                ledger_companies.get(ledger.company_code, ledger.date_to))
    plate_centres = {}
    for line in lines:
        for plate in line["project_plates"] | line["plates"]:
            if line["cost_centre"]:
                plate_centres.setdefault(plate, line["cost_centre"])
    used = set()
    for record in records:
        if not record["cost_centre"]:
            for plate in sorted(record["plates"]):
                if plate in plate_centres:
                    record["cost_centre"] = plate_centres[plate]
                    break
        hits, other_brand = _match(record, lines)
        if not hits:
            continue
        used.update(hits)
        matched = [lines[i] for i in hits]
        summary = _ledger_summary(matched)
        summary["refund"] = _refund(record, matched)
        record["ledger"] = sorted(hits)
        _apply_ledger(record, summary, other_brand)
    records.extend(_ledger_only(lines, used, classify))
    records = _drop_replaced(records)
    _fill_insurers(records)
    _alerts(records, ledger_companies, today)
    records = _fleets(records)
    month_end = _month_end(month_to) if month_to else None
    wanted = set(company_codes or ())
    kept = []
    for record in records:
        if wanted and record["company"] not in wanted:
            continue
        due = record["due"]
        if due and due < month_from:
            continue
        if due and month_end and due > month_end:
            continue
        kept.append(record)
    kept.sort(key=lambda r: (ORDER.index(r["category"])
                             if r["category"] in ORDER else 99,
                             r["due"] or datetime.date.max,
                             companies.order(r["company"]), r["object"]))
    for position, record in enumerate(kept, start=1):
        record["id"] = position
    used_lines = set()
    for record in kept:
        used_lines.update(record["ledger"])
    return _serialize(kept, lines, used_lines, ledgers, month_from,
                      month_to, company_codes, today)


def _refund(record, lines):
    """
    (date, amount) of the vehicle's own refund if it left the policy.
    ---
    El extorno del propio vehículo (apunte negativo que nombra su
    matrícula) si después no hay ningún cargo que la nombre: salió de la
    póliza. None si no.
    """
    own = [e for e in lines if record["plates"] & e["plates"]]
    refunds = [e for e in own if e["amount"] < 0]
    if not refunds:
        return None
    last = max(refunds, key=lambda e: e["date"])
    if any(e["amount"] > 0 and e["date"] > last["date"] for e in own):
        return None
    return _date(last["date"]), last["amount"]


def _apply_ledger(record, summary, other_brand):
    """
    What is paid wins: premium, paid-until and insurer from the ledger.
    ---
    Lo pagado manda: la prima anual, hasta cuándo está pagado y la
    aseguradora real salen del mayor; lo del documento queda para el
    aviso si no coincide.
    """
    record["ledger_until"] = summary["until"]
    record["ledger_last"] = summary["last"]
    if summary["refund"]:
        record["alerts"].append("Baja en la póliza")
        record["comments"].append(
            "En el mayor hay un extorno de %s € el %s: salió de la "
            "póliza." % (_eur(-summary["refund"][1]),
                         summary["refund"][0].strftime("%d/%m/%Y")))
        record["due"] = None
        record["premium"] = 0
        record["premium_source"] = "Mayor"
        record["origin"] = "Documento y mayor"
        return
    doc_premium = record["premium"]
    if summary["annual"]:
        record["premium"] = summary["annual"]
        record["premium_source"] = "Mayor"
    if doc_premium and summary["annual"] and min(
            abs(doc_premium - summary["annual"]),
            abs(doc_premium - summary["last"]),
            abs((record["receipt"] or 0) - summary["last"])) > (
                PRICE_TOLERANCE):
        record["alerts"].append("Precio distinto")
        record["comments"].append(
            "El documento da %s € y en el mayor se han pagado %s € en "
            "12 meses (último recibo %s €)." % (
                _eur(doc_premium), _eur(summary["annual"]),
                _eur(summary["last"])))
    if other_brand and summary["brands"]:
        record["alerts"].append("Aseguradora distinta")
        record["comments"].append(
            "El documento es de %s; en el mayor se paga a %s." % (
                record["insurer_doc"] or "otra aseguradora",
                ", ".join(summary["brands"])))
        record["insurer"] = summary["brands"][0]
    until = summary["until"]
    if until and (not record["due"] or (until - record["due"]).days > 20):
        if record["due"]:
            record["comments"].append(
                "Renovado según el mayor: pagado hasta el %s (el último "
                "documento vencía el %s)." % (
                    until.strftime("%d/%m/%Y"),
                    record["due"].strftime("%d/%m/%Y")))
        record["due"] = until
    record["origin"] = "Documento y mayor"


def _ledger_only(lines, used, classify):
    """
    Insurances found only in the ledger, grouped per vehicle or policy.
    ---
    Los seguros que solo están en el mayor, agrupados por matrícula del
    concepto, número de póliza o proyecto y aseguradora.
    """
    groups = collections.defaultdict(list)
    for entry in lines:
        if entry["i"] in used:
            continue
        if entry["plates"]:
            key = (entry["company"], "V", sorted(entry["plates"])[0],
                   entry["brand"])
        else:
            key = (entry["company"], "J", entry["project"], entry["brand"],
                   entry["numbers"][0] if entry["numbers"] else "")
        groups[key].append(entry)
    # Los apuntes sin número de la misma aseguradora y proyecto van con
    # la única póliza numerada que haya (los recibos dicen «NP. R.C.» y
    # la póliza «POL.60/2021/41034/0»).
    for key in [k for k in groups if k[1] == "J" and not k[4]]:
        numbered = [k for k in groups if k[:4] == key[:4] and k[4]]
        if len(numbered) == 1:
            groups[numbered[0]].extend(groups.pop(key))
    texts = {}
    for position, group in enumerate(groups.values()):
        last = group[-1]
        texts[str(position)] = "%s | %s | %s" % (
            last["insurer_text"], last["project_text"], last["concept"])
    categories = classify(list(texts.items())) if classify else {}
    records = []
    for position, group in enumerate(groups.values()):
        if abs(sum(e["amount"] for e in group)) < 0.01:
            continue
        summary = _ledger_summary(group)
        last = max(group, key=lambda e: e["date"])
        plates = set().union(*(e["plates"] for e in group))
        cost_centres = sorted({e["cost_centre"] for e in group
                               if e["cost_centre"]})
        records.append({
            "category": categories.get(str(position), "otros"),
            "company": last["company"],
            "machine_id": None,
            "machine_active": None,
            "cost_centre": cost_centres[0] if cost_centres else "",
            "code": cost_centres[0] if cost_centres else "",
            "plate": ", ".join(sorted(plates)),
            "plates": plates,
            "object": " · ".join(p for p in (
                cost_centres[0] if cost_centres else "",
                last["concept"], last["project_text"]) if p),
            "insurer": summary["brands"][0] if summary["brands"] else "",
            "insurer_doc": "",
            "broker": "",
            "policy": last["numbers"][0] if last["numbers"] else "",
            "cover": "",
            "due": summary["until"],
            "premium": summary["annual"],
            "premium_source": "Mayor",
            "receipt": summary["last"],
            "frequency": "",
            "previous": None,
            "notes": "",
            "documents": [],
            "origin": "Mayor",
            "ledger": [e["i"] for e in group],
            "ledger_until": summary["until"],
            "ledger_last": summary["last"],
            "alerts": [],
            "comments": ["No hay documento de este seguro en el panel: "
                         "sale del libro mayor."],
        })
    return records


def _drop_replaced(records):
    """
    Drop an insurance replaced by a later one of the same vehicle.
    ---
    Quita el seguro que ya sustituye otro posterior del mismo vehículo
    y tipo (p. ej. el A39 que pasó de Generali a Allianz): el nuevo se
    queda con una nota de con quién estaba antes.
    """
    keep = []
    for record in records:
        if record["category"] != "circulacion" or not record["due"]:
            keep.append(record)
            continue
        newer = [
            other for other in records
            if other is not record and other["category"] == "circulacion"
            and other["due"] and other["due"] > record["due"]
            and other["insurer"] != record["insurer"]
            and ((record["machine_id"]
                  and other["machine_id"] == record["machine_id"])
                 or (record["plates"] & other["plates"]))]
        if newer and (newer[0]["due"] - record["due"]).days > 180:
            newer[0]["comments"].append(
                "Antes estaba con %s (hasta el %s)." % (
                    record["insurer"] or "otra aseguradora",
                    record["due"].strftime("%d/%m/%Y")))
            continue
        keep.append(record)
    return keep


def _alerts(records, ledger_companies, today):
    """
    The warnings of each insurance.
    ---
    Avisos de cada seguro: vencido o sin renovar, doble seguro del mismo
    vehículo, vehículo de baja asegurado, sin precio y sin recibo en el
    mayor de su empresa.
    """
    by_plate = collections.defaultdict(list)
    for record in records:
        if record["category"] == "circulacion":
            for plate in record["plates"]:
                by_plate[plate].append(record)
    for record in records:
        due = record["due"]
        if due and due < today:
            record["alerts"].insert(0, "Vencido")
            record["comments"].append(
                "Venció el %s y no hay documento ni recibo posterior." %
                due.strftime("%d/%m/%Y"))
        if record["machine_active"] is False and due and due >= today:
            record["alerts"].append("Vehículo de baja")
            record["comments"].append(
                "El centro de gasto está de baja y el seguro sigue en "
                "vigor hasta el %s." % due.strftime("%d/%m/%Y"))
        if record["premium"] is None or (
                not record["premium"]
                and "Baja en la póliza" not in record["alerts"]):
            record["alerts"].append("Sin precio")
        covered = ledger_companies.get(record["company"])
        if (record["origin"] == "Documento" and covered and due
                and due - datetime.timedelta(days=365) <= covered):
            record["alerts"].append("Sin recibo en el mayor")
    for plate, group in by_plate.items():
        alive = [r for r in group if r["due"] and r["due"] >= today
                 and "Baja en la póliza" not in r["alerts"]
                 and _known(r["insurer"])]
        # Doble seguro: dos aseguradoras distintas (Caser y Helvetia son
        # la misma) con números de póliza distintos (S152: la flota C6
        # A96 0000252 leída unas veces como Helvetia y otras como Caser).
        doubled = [r for r in alive if any(
            _insurer_group(r["insurer"]) != _insurer_group(o["insurer"])
            and _digits(r["policy"]) != _digits(o["policy"])
            for o in alive)]
        if not doubled:
            continue
        names = ", ".join(sorted({"%s (%s)" % (
            r["insurer"], companies.label(r["company"]))
            for r in doubled}))
        for record in doubled:
            if "Doble seguro" not in record["alerts"]:
                record["alerts"].append("Doble seguro")
                record["comments"].append(
                    "La matrícula %s tiene seguro con %s a la vez." % (
                        plate, names))


def _fleets(records):
    """
    Fold the vehicles of one fleet policy into one line.
    ---
    Las flotas (FLEET_MIN_VEHICLES vehículos o más con el mismo número
    de póliza y aseguradora) se pliegan en una línea con la suma de
    primas y el detalle de cada vehículo.
    """
    groups = collections.defaultdict(list)
    for record in records:
        policy = _digits(record["policy"])
        if record["category"] == "circulacion" and len(policy) >= 5 and (
                record["machine_id"] or record["plate"]):
            groups[(record["company"],
                    _insurer_group(record["insurer"]), policy)].append(
                record)
    folded = set()
    result = []
    for (company, insurer, _policy), group in groups.items():
        if len(group) < FLEET_MIN_VEHICLES:
            continue
        folded.update(id(r) for r in group)
        dues = collections.Counter(r["due"] for r in group if r["due"])
        due = dues.most_common(1)[0][0] if dues else None
        alerts = []
        for record in group:
            for alert in record["alerts"]:
                if alert not in alerts:
                    alerts.append(alert)
        result.append({
            **group[0],
            "object": "Flota de %d vehículos" % len(group),
            "plate": "",
            "plates": set().union(*(r["plates"] for r in group)),
            "code": "",
            "cost_centre": "",
            "machine_id": None,
            "due": due,
            "premium": round(sum(r["premium"] or 0 for r in group), 2),
            "previous": None,
            "alerts": alerts,
            "comments": [c for r in group for c in r["comments"]],
            "documents": [d for r in group for d in r["documents"]],
            "ledger": sorted({i for r in group for i in r["ledger"]}),
            "fleet": sorted(
                [(r["object"], r["premium"], r["due"]) for r in group],
                key=lambda v: v[0]),
        })
    result.extend(r for r in records if id(r) not in folded)
    return result


def _month_end(day):
    following = (day.replace(day=28) + datetime.timedelta(days=4))
    return following - datetime.timedelta(days=following.day)


def _eur(value):
    text = "{:,.2f}".format(value or 0)
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _serialize(records, lines, used_lines, ledgers, month_from, month_to,
               company_codes, today):
    def iso(day):
        return day.isoformat() if day else None

    out = []
    for record in records:
        out.append({
            "id": record["id"],
            "category": record["category"],
            "category_label": CATEGORY_LABELS.get(record["category"],
                                                  "Otros"),
            "company": record["company"],
            "company_label": companies.label(record["company"]) or (
                "Sin empresa"),
            "object": record["object"],
            "code": record["code"],
            "plate": record["plate"],
            "insurer": record["insurer"] or "No consta",
            "insurer_doc": record["insurer_doc"],
            "broker": record["broker"] or "No consta",
            "policy": record["policy"] or "No consta",
            "cover": record["cover"],
            "due": iso(record["due"]),
            "days": (record["due"] - today).days if record["due"] else None,
            "premium": record["premium"],
            "premium_source": record["premium_source"],
            "receipt": record.get("ledger_last") or record["receipt"],
            "ledger_until": iso(record.get("ledger_until")),
            "frequency": record["frequency"],
            "previous": record["previous"],
            "change": (round((record["premium"] / record["previous"] - 1)
                             * 100, 1)
                       if record["premium"] and record["previous"]
                       else None),
            "notes": record["notes"],
            "alerts": record["alerts"],
            "comments": record["comments"],
            "origin": record["origin"],
            "documents": record["documents"],
            "ledger": record["ledger"],
            "fleet": [[name, premium, iso(due)] for name, premium, due
                      in record.get("fleet", [])],
        })
    ledger_rows = []
    for entry in lines:
        ledger_rows.append({
            "i": entry["i"],
            "company": entry["company"],
            "company_label": companies.label(entry["company"]),
            "project": entry["project"],
            "project_text": entry["project_text"],
            "insurer": entry["brand"],
            "insurer_text": entry["insurer_text"],
            "date": entry["date"],
            "covered_until": entry["covered_until"],
            "concept": entry["concept"],
            "amount": entry["amount"],
            "in_report": entry["i"] in used_lines,
        })
    return {
        "today": today.isoformat(),
        "month_from": month_from.isoformat(),
        "month_to": iso(month_to),
        "companies": list(company_codes or ()),
        "ledgers": [{
            "id": ledger.pk, "company": ledger.company_code,
            "company_label": companies.label(ledger.company_code),
            "date_from": iso(ledger.date_from),
            "date_to": iso(ledger.date_to),
            "name": ledger.original_name,
        } for ledger in ledgers],
        "records": out,
        "ledger_lines": ledger_rows,
    }
