# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_machines.py
"""
Cost centres: intake, status and deletion, new interface (S163).

---

Centros de gasto en la nueva interfaz (S163), copiado de
panel/views_machine_intake.py (alta por documentos) y fleet/views.py
(alta, baja/reactivar y borrar, uno y en masa):
- Alta: se suben sus documentos (permiso de circulación, ficha técnica,
  seguro...), «Leer» rellena matrícula, bastidor, marca y modelo y
  seguro, se completa y se crea; sus documentos van a su carpeta y
  baja su carpeta local. Si la matrícula o el bastidor son de una de
  baja, se reactiva.
- A los marcados: dar de baja, reactivar (su documentación y su carpeta
  local siguen al estado) o borrar (solo las que no tienen partes).
"""
import re

from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.views import View

from document_explorer import machine_local_folder_service
from document_explorer.document_check_service import (
    merge_machine_facts,
    normalize_plate,
    read_machine_document,
)
from document_explorer.machine_folder_service import sync_machine_documents
from fleet.models import MachineAsset
from new_ui.forms import MachineAssetForm
from new_ui.mixins import SuperuserRequiredMixin

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


class MachineIntakeExtractView(SuperuserRequiredMixin, View):
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


# ----------------------------------------------------------------- avisos
def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


class NuiMachineIntakeExtractView(MachineIntakeExtractView):
    """Lectura del alta, con el aviso de Acciones."""

    def post(self, request):
        import json

        response = super().post(request)
        data = json.loads(response.content or b"{}")
        if not data.get("ok"):
            data["message"] = data.get("error") or "No se han podido leer."
        elif data.get("duplicate"):
            data["message"] = ("Ya existe y está activa: %s." %
                               data["duplicate"])
        elif data.get("reactivate"):
            data["message"] = ("Es de una máquina de baja: %s. Al confirmar, "
                               "se reactiva." % data["reactivate"]["label"])
        else:
            data["message"] = "Datos leídos: revísalos y crea la máquina."
        return JsonResponse(data, status=response.status_code)


class MachineCreateView(SuperuserRequiredMixin, View):
    """
    POST: create a cost centre (or reactivate an inactive one).

    ---

    POST: crea el centro de gasto con el formulario de siempre (o
    reactiva el de baja indicado en `reactivate_machine_id`, completando
    sus datos vacíos), guarda los documentos del alta y crea su carpeta
    local. La vista se queda con la máquina.
    """

    def post(self, request):
        company_user = request.user.company_user
        company = company_user.company
        reactivate_pk = request.POST.get("reactivate_machine_id", "")
        if reactivate_pk.isdigit():
            asset = MachineAsset.objects.filter(
                pk=int(reactivate_pk), company=company,
                is_active=False).first()
            if asset is None:
                return _error("Esa máquina ya no está de baja.")
            previous_local = (
                machine_local_folder_service.current_local_folder(asset))
            fields = ["is_active"]
            asset.is_active = True
            for name in ("plate", "chassis_number", "brand_model",
                         "insurance_info"):
                value = request.POST.get(name, "").strip()[:100 if (
                    name == "insurance_info") else 200]
                if value and not (getattr(asset, name) or "").strip():
                    setattr(asset, name, value)
                    fields.append(name)
            asset.save(update_fields=fields)
            sync_machine_documents(asset)
            machine_local_folder_service.follow_change(
                asset, previous_local, requested_by=company_user)
            stored, warnings = store_intake_documents(request, asset)
            return self._done(asset, "Reactivada", stored, warnings)
        form = MachineAssetForm(request.POST, company=company)
        if not form.is_valid():
            errors = ["%s: %s" % (
                form.fields[name].label if name in form.fields else name,
                " ".join(messages))
                for name, messages in form.errors.items()]
            return _error("No se ha creado: %s" % "; ".join(errors))
        asset = form.save(commit=False)
        asset.company = company
        asset.code = asset.code.strip().upper()
        asset.insurance_info = request.POST.get(
            "insurance_info", "").strip()[:100]
        asset.save()
        machine_local_folder_service.create_for_machine(
            asset, requested_by=company_user, always=True)
        stored, warnings = store_intake_documents(request, asset)
        return self._done(asset, "Alta hecha", stored, warnings)

    @staticmethod
    def _done(asset, what, stored, warnings):
        label = "%s — %s" % (asset.code, asset.brand_model or "")
        message = "%s: %s; %d documento(s) guardados." % (what, label, stored)
        if warnings:
            message += " " + " ".join(warnings)
        return _ok(message, scope={"pk": asset.pk, "label": label})


def _marked(request):
    company = request.user.company_user.company
    ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
    return MachineAsset.objects.filter(company=company, pk__in=ids)


class MachineBulkStatusView(SuperuserRequiredMixin, View):
    """
    POST `action` (deactivate | reactivate) on the marked machines.

    ---

    POST: da de baja o reactiva las marcadas, una a una: su
    documentación pasa a ACTIVAS/INACTIVAS y su carpeta local la sigue.
    Nunca borra nada.
    """

    def post(self, request):
        company_user = request.user.company_user
        action = request.POST.get("action", "")
        if action not in ("deactivate", "reactivate"):
            return _error("Acción no válida.")
        target = action == "reactivate"
        updated = 0
        for asset in _marked(request).exclude(is_active=target):
            previous_local = (
                machine_local_folder_service.current_local_folder(asset))
            asset.is_active = target
            asset.save(update_fields=["is_active"])
            sync_machine_documents(asset)
            machine_local_folder_service.follow_change(
                asset, previous_local, requested_by=company_user)
            updated += 1
        return _ok("%d centro(s) de gasto %s." % (
            updated, "reactivados" if target else "dados de baja"))


class MachineBulkDeleteView(SuperuserRequiredMixin, View):
    """
    POST: delete the marked machines that have no work-order lines.

    ---

    POST: borra definitivamente las marcadas que no tienen partes de
    trabajo; las que los tienen no se tocan (para esas, dar de baja).
    """

    def post(self, request):
        selected = _marked(request)
        in_use = sorted(set(selected.filter(
            work_order_lines__isnull=False).values_list("code", flat=True)))
        deletable = selected.exclude(code__in=in_use)
        deleted = deletable.count()
        deletable.delete()
        message = "%d centro(s) de gasto borrados." % deleted
        if in_use:
            message += (" No se tocan por tener partes (usa «Dar de baja»): "
                        "%s." % ", ".join(in_use))
        return _ok(message) if deleted else _error(message)


def machines_context(section, company):
    """Formulario de alta vacío (solo Centros de gasto)."""
    if section != "cdg":
        return {}
    return {"machine_new_form": MachineAssetForm(company=company)}
