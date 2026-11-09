# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_intake.py
"""
Machine intake from its documents (H31, S148): the same as the people
intake, for cost centres.

---

Alta de máquina por documentos (H31, S148). Miguel Ángel: "continuamos
con la maquinaria y extrapolamos las funcionalidades" del alta de
Personal. Se suben el permiso de circulación, la ficha técnica, el
seguro... el sistema lee matrícula, bastidor, marca y modelo y seguro
(cada dato solo de los tipos que lo acreditan) y rellena el formulario
de alta; al crear, los documentos se guardan en su carpeta y bajan a
su carpeta local. Si la matrícula o el bastidor ya son de una máquina
de baja, se ofrece reactivarla; si está activa, se bloquea.
"""
import re

from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.views import View

from document_explorer.document_check_service import (
    merge_machine_facts,
    normalize_plate,
    read_machine_document,
)
from fleet.models import MachineAsset
from panel.mixins import FleetManageAccessMixin

MAX_INTAKE_FILES = 20


def _plain_chassis(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def find_existing(company, plate, chassis):
    """
    The machine of the company with this plate or chassis, if any.
    ---
    La máquina de la empresa con esta matrícula o bastidor, si la hay.
    """
    plate = normalize_plate(plate)
    chassis = _plain_chassis(chassis)
    if not plate and not chassis:
        return None
    for machine in MachineAsset.objects.filter(company=company).only(
        "pk", "code", "plate", "chassis_number", "brand_model", "is_active",
    ):
        if plate and normalize_plate(machine.plate) == plate:
            return machine
        if chassis and len(chassis) >= 8 and (
            _plain_chassis(machine.chassis_number) == chassis
        ):
            return machine
    return None


def machine_label(machine):
    return " ".join(
        part for part in (machine.code, machine.plate, machine.brand_model)
        if part
    )


class MachineIntakeExtractView(FleetManageAccessMixin, View):
    """
    POST documents: their type and the draft of the machine.
    ---
    POST con los documentos: el tipo de cada uno y el borrador de la
    máquina (matrícula, bastidor, marca y modelo, seguro).
    """

    def post(self, request):
        files = request.FILES.getlist("documents")
        if not files:
            return JsonResponse(
                {"ok": False, "error": "Selecciona al menos un documento."},
                status=400,
            )
        if len(files) > MAX_INTAKE_FILES:
            return JsonResponse({
                "ok": False,
                "error": "Máximo %d documentos en el alta." % (
                    MAX_INTAKE_FILES),
            }, status=400)
        readings, per_file = [], []
        for uploaded in files:
            try:
                reading = read_machine_document(uploaded.read(), uploaded.name)
            except Exception:  # noqa: BLE001 -- un archivo no para el resto
                reading = {"code": "", "label": "", "facts": {}}
            readings.append(reading)
            per_file.append({
                "name": uploaded.name,
                "document_type_code": reading["code"],
                "document_type_label": reading["label"] or "Sin reconocer",
            })
        draft = merge_machine_facts(readings)
        company = request.user.company_user.company
        existing = find_existing(
            company, draft.get("plate"), draft.get("chassis_number"),
        )
        payload = {"ok": True, "draft": draft, "per_file": per_file}
        if existing is not None and existing.is_active:
            payload["duplicate"] = machine_label(existing)
        elif existing is not None:
            payload["reactivate"] = {
                "id": existing.pk, "label": machine_label(existing),
                "code": existing.code,
            }
        return JsonResponse(payload)


def store_intake_documents(request, machine):
    """
    Store the intake documents in the machine's folder.

    Returns (stored, warnings).
    ---
    Guarda los documentos del alta en la carpeta de la máquina, con el
    tipo leído (los no reconocidos no se guardan: se avisa). Devuelve
    (guardados, avisos).
    """
    from document_explorer.models import DocumentTypeCatalog
    from document_explorer.subject_upload_service import (
        SubjectUploadError,
        upload_subject_document,
    )

    files = request.FILES.getlist("documents")
    codes = request.POST.getlist("document_type_codes")
    types = {
        doc_type.code: doc_type
        for doc_type in DocumentTypeCatalog.objects.filter(
            code__in=[code for code in codes if code], is_active=True,
        )
    }
    machine_ct = ContentType.objects.get_for_model(MachineAsset)
    label = "%s -- %s" % (machine.code, machine.brand_model)
    stored, warnings = 0, []
    for index, uploaded in enumerate(files):
        code = codes[index] if index < len(codes) else ""
        document_type = types.get(code)
        if document_type is None:
            warnings.append(
                "%s: tipo sin reconocer, súbelo desde su ficha." % (
                    uploaded.name))
            continue
        try:
            upload_subject_document(
                subject=machine, domain_content_type=machine_ct,
                document_type=document_type, data=uploaded.read(),
                original_filename=uploaded.name, typed_date=None,
                subject_label=label,
                uploaded_by=request.user.company_user,
            )
            stored += 1
        except SubjectUploadError as exc:
            warnings.append("%s: %s" % (uploaded.name, exc))
    return stored, warnings
