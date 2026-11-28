# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/views_qr.py
"""
H23 (S154, invasora) -- public page of a cost centre's QR code.

---

H23 (S154, invasora) -- página a la que lleva el QR de un centro de
gasto: ficha técnica, cómo se cuenta la revisión, observaciones, fotos
y vídeos. Sin inicio de sesión (el trabajador la abre con el móvil al
leer el QR); solo lectura y solo se llega con el identificador del QR,
que no se puede adivinar.
"""
from django.http import Http404
from django.shortcuts import render

from fleet import qr_sheet_service as qr
from fleet.manual_counters_service import image_rows, manual_rows
from fleet.models import MachineQrSheet


def qr_public_view(request, token):
    """
    GET: the sheet of the cost centre behind this QR.

    ---

    GET: la ficha del centro de gasto de este QR.
    """
    sheet = MachineQrSheet.objects.select_related("machine").filter(
        token=token).first()
    if sheet is None:
        raise Http404("Código QR desconocido.")
    machine = sheet.machine
    return render(request, "fleet/qr_public.html", {
        "machine": machine,
        "sheet": sheet,
        "specs": qr.spec_rows(machine),
        "service_lines": qr.service_lines(machine),
        "media": qr.media_rows(sheet),
        # S154 (28/11): dónde mirar los contadores, de los manuales.
        "counter_images": image_rows(machine),
        "manuals": manual_rows(machine),
    })
