# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/history/views.py
"""
Views for the machine history module (Hito 22).
Provides read-only access to intervention history per machine asset
for WORKSHOP role users.
---
Vistas para el modulo de historial de maquinas (Hito 22).
Proporciona acceso de solo lectura al historial de intervenciones
por maquina para rol WORKSHOP.
"""
from datetime import date, timedelta

from django.db.models import Sum
from django.views.generic import View
from django.shortcuts import render

from fleet.models import MachineAsset
from panel.mixins import CompanyUserRequiredMixin
from spare_parts.gcs_service import (
    MACHINE_DOCUMENTS_BUCKET,
    TASK_PHOTOS_BUCKET,
    generate_signed_url,
)
from work_order_processor.models import (
    FaultCategory,
    FaultSubcategory,
    WorkOrderEntry,
    WorkOrderEntryLine,
)

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fault category display maps — reused from analytics app
# Mapas de visualizacion de categoria de averia — reutilizados de analytics
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fault category display maps -- built directly from the model's
# TextChoices (work_order_processor.models.FaultCategory /
# FaultSubcategory), NOT a hand-maintained duplicate dict.
#
# BUG FIXED 2026-07-14: this file used to keep its own hardcoded copy of
# these maps, using an OLD taxonomy (MECHANICAL/ELECTRICAL/HYDRAULIC/
# BODYWORK/TIRES/MAINTENANCE/OTHER, unprefixed subcategories) that never
# got updated when the real taxonomy evolved to the current 8-category/
# prefixed scheme (ENGINE_TRANSMISSION, HY_VALVES, BSS_STEERING, etc. --
# see FaultCategory/FaultSubcategory in work_order_processor/models.py).
# Miguel Ángel spotted raw codes like "ENGINE_TRANSMISSION" and "HY_VALVES"
# showing untranslated in the Historial de Máquina table. analytics/views.py
# had its own THIRD copy of this same taxonomy (already correct, but a
# separate duplicate all the same) -- building the maps from the model's
# TextChoices here removes this file's copy from the duplication entirely,
# so it can never drift out of sync with the model again.
# ---
# Mapas de visualización de categoría de avería -- construidos
# directamente desde los TextChoices del modelo
# (work_order_processor.models.FaultCategory / FaultSubcategory), NO un
# dict duplicado mantenido a mano.
#
# BUG CORREGIDO 2026-07-14: este archivo mantenía su propia copia
# hardcodeada de estos mapas, con una taxonomía ANTIGUA (MECHANICAL/
# ELECTRICAL/HYDRAULIC/BODYWORK/TIRES/MAINTENANCE/OTHER, subcategorías
# sin prefijo) que nunca se actualizó cuando la taxonomía real evolucionó
# al esquema actual de 8 categorías/subcategorías con prefijo
# (ENGINE_TRANSMISSION, HY_VALVES, BSS_STEERING, etc. -- ver
# FaultCategory/FaultSubcategory en work_order_processor/models.py).
# Miguel Ángel detectó códigos en crudo como "ENGINE_TRANSMISSION" y
# "HY_VALVES" sin traducir en la tabla de Historial de Máquina.
# analytics/views.py tenía su propia TERCERA copia de esta misma
# taxonomía (ya correcta, pero un duplicado más igualmente) --
# construir los mapas aquí desde los TextChoices del modelo elimina la
# copia de este archivo de la duplicación por completo, así que ya no
# puede volver a desincronizarse del modelo.
# ---------------------------------------------------------------------------

_FAULT_CAT_MAP = dict(FaultCategory.choices)
_FAULT_CAT_MAP[None] = "—"
_FAULT_CAT_MAP[""] = "—"

_FAULT_SUBCAT_LABELS = dict(FaultSubcategory.choices)
_FAULT_SUBCAT_LABELS[None] = "—"
_FAULT_SUBCAT_LABELS[""] = "—"

# ---------------------------------------------------------------------------
# Default date range: last 365 days
# Rango de fechas por defecto: últimos 365 días
# ---------------------------------------------------------------------------

_DEFAULT_DAYS = 365

class MachineHistoryView(CompanyUserRequiredMixin, View):
    """
    Read-only view for consulting the intervention and breakdown-ticket
    history of any active machine asset in the company. Originally
    WORKSHOP-only (Hito 22); widened in H7/S016 (confirmed explicitly by
    Miguel Ángel) to every role -- ADMIN, SUPERVISOR, WORKSHOPBOSS,
    WORKSHOP and DRIVER -- since the page carries no mutable action of
    any kind.

    GET parameters:
      machine_code — code of the MachineAsset to inspect (optional).
      date_from    — YYYY-MM-DD start of range (default: today - 365 days).
      date_to      — YYYY-MM-DD end of range (default: today).

    Returns a chronological (descending) list of WorkOrderEntryLine records
    filtered by machine and date range, plus a summary header with totals,
    plus (H7/S016) the full BreakdownTicket history for the machine with
    each ticket's combined photo gallery (WhatsApp photos + task photos).
    No cost data is ever exposed.
    ---
    Vista de solo lectura para consultar el historial de intervenciones y
    de tickets de avería de cualquier máquina activa de la empresa.
    Originalmente exclusiva de WORKSHOP (Hito 22); ampliada en H7/S016
    (confirmado explícitamente por Miguel Ángel) a todos los roles --
    ADMIN, SUPERVISOR, WORKSHOPBOSS, WORKSHOP y DRIVER -- al no llevar
    ninguna acción mutable.

    Parametros GET:
      machine_code — codigo del MachineAsset a inspeccionar (opcional).
      date_from    — YYYY-MM-DD inicio del rango (por defecto: hoy - 365 dias).
      date_to      — YYYY-MM-DD fin del rango (por defecto: hoy).

    Devuelve una lista cronologica (descendente) de registros
    WorkOrderEntryLine filtrados por maquina y rango de fechas,
    mas un resumen de cabecera con totales, mas (H7/S016) el historial
    completo de BreakdownTicket de la maquina con la galeria de fotos
    combinada de cada ticket (fotos de WhatsApp + fotos de tarea).
    Sin exposicion de datos de coste.
    """

    template_name = "panel/machine_history.html"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_company(self, request):
        """
        Returns the company scoped to the authenticated user.
        ---
        Retorna la empresa del usuario autenticado.
        """
        return request.user.company_user.company

    def _parse_date(self, raw, fallback):
        """
        Parses a YYYY-MM-DD string; returns fallback on any error.
        ---
        Parsea una cadena YYYY-MM-DD; retorna fallback ante cualquier error.
        """
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return fallback

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(self, request, *args, **kwargs):
        """
        Renders the machine history page.
        Fetches WorkOrderEntryLine records for the selected machine and
        date range. Computes summary totals (count, hours, last date).
        ---
        Renderiza la pagina de historial de maquina.
        Obtiene registros WorkOrderEntryLine para la maquina y rango
        de fechas seleccionados. Calcula totales del resumen (contador,
        horas, ultima fecha).
        """
        company = self._get_company(request)
        company_user = request.user.company_user

        today = date.today()
        default_from = today - timedelta(days=_DEFAULT_DAYS)

        # -- Parse GET params -----------------------------------------------
        machine_code_raw = (
            request.GET.get("machine_code", "").strip().upper()
        )
        date_from = self._parse_date(
            request.GET.get("date_from", "").strip(), default_from
        )
        date_to = self._parse_date(
            request.GET.get("date_to", "").strip(), today
        )

        # Swap if inverted
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        # -- Machine queryset scoped to company -----------------------------
        machines = MachineAsset.objects.filter(
            company=company,
            is_active=True,
        )

        # -- Resolve selected machine by code -------------------------------
        selected_machine = None
        if machine_code_raw:
            selected_machine = machines.filter(
                code=machine_code_raw
            ).first()

        # -- History query --------------------------------------------------
        lines = []
        total_intervenciones = 0
        total_horas = None
        ultima_intervencion = None

        if selected_machine is not None:
            qs = (
                WorkOrderEntryLine.objects.filter(
                    machine_asset=selected_machine,
                    entry__work_date__range=(date_from, date_to),
                )
                .select_related(
                    "entry",
                    "entry__work_order",
                )
                .order_by(
                    "-entry__work_date",
                    "-entry__work_order__id",
                )
            )

            # Enrich with translated labels before passing to template
            # Enriquecer con etiquetas traducidas antes de pasar al template
            enriched = []
            for line in qs:
                enriched.append(
                    {
                        "work_date": line.entry.work_date,
                        "worker_name": line.entry.worker_name,
                        "fault_category_display": _FAULT_CAT_MAP.get(
                            line.fault_category,
                            line.fault_category or "—",
                        ),
                        "fault_subcategory_display": (
                            _FAULT_SUBCAT_LABELS.get(
                                line.fault_subcategory,
                                line.fault_subcategory or "—",
                            )
                        ),
                        "fault_description": (
                            line.fault_description or "—"
                        ),
                        "repair_notes": line.repair_notes or "—",
                        "delta_hours": line.delta_hours,
                        "or_val": line.or_val,
                    }
                )

            lines = enriched
            total_intervenciones = len(enriched)

            # Summary aggregates
            agg = qs.aggregate(
                suma_horas=Sum("delta_hours"),
                ultima=django_max("entry__work_date"),
            )
            total_horas = agg["suma_horas"]
            ultima_intervencion = agg["ultima"]

        # -- Ticket history (H7/S016) ----------------------------------
        # Fichas de averia de la maquina, con su galeria combinada de
        # fotos (photos JSONField de WhatsApp + task_photos de H7).
        # Independiente del rango de fechas de arriba -- se muestra el
        # historial completo de tickets, no solo el periodo consultado.
        tickets = []
        if selected_machine is not None:
            tickets = (
                selected_machine.breakdown_tickets
                .prefetch_related("task_photos")
                .order_by("-created_at")
            )
            # URL de descarga resuelta aquí (S022, directriz de
            # plantillas tontas): gcs_blob_name -> URL firmada bajo
            # demanda; drive_web_link (legado) se usa tal cual.
            for ticket in tickets:
                for photo in ticket.task_photos.all():
                    photo.download_url = None
                    if photo.gcs_blob_name:
                        try:
                            photo.download_url = generate_signed_url(
                                TASK_PHOTOS_BUCKET, photo.gcs_blob_name,
                            )
                        except Exception:
                            logger.exception(
                                "# [MachineHistoryView] Fallo generando "
                                "URL firmada para TaskPhoto #%d "
                                "(blob=%s).",
                                photo.pk, photo.gcs_blob_name,
                            )
                    elif photo.drive_web_link:
                        photo.download_url = photo.drive_web_link

        # -- Cost-center documentation (H23) --------------------------------
        # Integrada aquí en vez de en un listado global cruzando las
        # 400 máquinas de la empresa (decisión de Miguel Ángel,
        # sesión H23: "por centro de gasto, no un listado gigante") --
        # mismo precedente que la galería de fotos de tarea (H7) fusionada
        # en esta misma vista en vez de crear una página separada.
        # ---
        # Integrated here instead of a global listing crossing the
        # company's 400 machines (Miguel Ángel's decision, H23 session:
        # "per cost centre, not one giant listing") -- same precedent as
        # the task-photo gallery (H7) merged into this same view instead
        # of a separate page.
        documents = []
        if selected_machine is not None:
            documents = (
                selected_machine.documents
                .order_by("-created_at")
            )
            for document in documents:
                document.download_url = None
                if document.gcs_blob_name:
                    try:
                        document.download_url = generate_signed_url(
                            MACHINE_DOCUMENTS_BUCKET, document.gcs_blob_name,
                        )
                    except Exception:
                        logger.exception(
                            "# [MachineHistoryView] Fallo generando URL "
                            "firmada para MachineDocument #%d (blob=%s).",
                            document.pk, document.gcs_blob_name,
                        )
                elif document.drive_web_link:
                    document.download_url = document.drive_web_link

        context = {
            "company": company,
            "company_user": company_user,
            "own_presence": self._get_own_presence(request),
            "active_nav": "machine_history",
            "today": today,
            # Selector data
            "selected_machine": selected_machine,
            "machine_code": machine_code_raw,
            # Date range
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            # Results
            "lines": lines,
            "has_results": selected_machine is not None,
            "tickets": tickets,
            # Documentación de centro de gasto (H23)
            "documents": documents,
            "can_upload_documents": company_user.role in {
                company_user.ROLE_DOCS_SUPERVISOR, company_user.ROLE_ADMIN,
            },
            # Summary
            "total_intervenciones": total_intervenciones,
            "total_horas": total_horas,
            "ultima_intervencion": ultima_intervencion,
        }
        return render(request, self.template_name, context)

    # ------------------------------------------------------------------
    # Presence helper (same pattern as panel views)
    # Helper de presencia (mismo patron que las vistas del panel)
    # ------------------------------------------------------------------

    def _get_own_presence(self, request):
        """
        Returns the current active PresenceStatus for the authenticated user,
        or None if no active status exists.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado,
        o None si no existe estado activo.
        """
        from django.db.models import Q
        from django.utils.timezone import now as tz_now
        from ivr_config.models import PresenceStatus

        cu = request.user.company_user
        return (
            PresenceStatus.objects.filter(
                company_user=cu,
                starts_at__lte=tz_now(),
            )
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=tz_now()))
            .order_by("-starts_at")
            .first()
        )


# ---------------------------------------------------------------------------
# Local alias for django.db.models.Max — avoids top-level import collision
# Alias local para django.db.models.Max — evita colision con import global
# ---------------------------------------------------------------------------

def django_max(field):
    """
    Returns a Max() aggregate expression for the given field.
    Used to avoid name collision with Python built-in max().
    ---
    Retorna una expresion agregada Max() para el campo dado.
    Se usa para evitar colision con el built-in max() de Python.
    """
    from django.db.models import Max
    return Max(field)


