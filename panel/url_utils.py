# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/url_utils.py
"""
Shared helper for validating back_url redirect targets across panel views.

Used to preserve the active filter set (operator, dates, machine, etc.)
when the user navigates away from WorkOrderAdminHistoryView (edit a
digital part, view a reviewed part's detail) and back -- gap flagged by
Miguel Ángel 2026-07-21: filters were lost on every return-to-list
redirect after the H17 S012 view unification.

---

Helper compartido para validar destinos de redirección back_url en las
vistas de panel.

Se usa para preservar el conjunto de filtros activos (operario, fechas,
máquina, etc.) cuando el usuario navega fuera de WorkOrderAdminHistoryView
(editar un parte digital, ver el detalle de un parte revisado) y vuelve --
gap señalado por Miguel Ángel 2026-07-21: los filtros se perdían en todos
los redirect de vuelta al listado tras la unificación de vistas de H17 S012.
"""
from django.utils.http import url_has_allowed_host_and_scheme


def safe_back_url(request, raw, fallback):
    """
    Returns raw if it is a safe, same-host relative URL (prevents
    open-redirect via a tampered back_url param/field); otherwise
    returns fallback.
    ---
    Devuelve raw si es una URL relativa segura del mismo host (previene
    open-redirect vía un parámetro/campo back_url manipulado); si no,
    devuelve fallback.
    """
    raw = (raw or "").strip()
    if raw and url_has_allowed_host_and_scheme(
        url=raw,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return raw
    return fallback
