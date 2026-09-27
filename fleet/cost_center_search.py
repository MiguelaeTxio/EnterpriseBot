# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/cost_center_search.py
"""
Shared search of cost centres (MachineAsset) typed by code, brand/model
or plate -- one single rule for every screen that lets a user type a
cost-centre code and pick it from the matching ones.

---

Búsqueda compartida de centros de gasto (MachineAsset) escribiendo
código, marca/modelo o matrícula -- una sola regla para toda pantalla
en la que el usuario escribe el código de un CdG y lo elige entre los
que coinciden. Extraída en S121 de WorkshopAssetAutocompleteView (parte
diario digital) para que la entrega de accesorios de elevación use
exactamente el mismo sistema, como pidió Miguel Ángel.
"""

from django.db.models import Q

from fleet.models import MachineAsset

# Solo con 4 o más dígitos se busca además la subcadena de dígitos en
# la matrícula ("1234" encuentra "AB1234C"); con menos, demasiados
# falsos positivos (regla original del parte diario).
_MIN_PLATE_DIGITS = 4


def search_cost_centers(company, query, limit=20):
    """
    Active cost centres of the company matching `query`, by code.
    ---
    Centros de gasto activos de la empresa que coinciden con `query`
    (código, marca/modelo o matrícula; y, con 4 o más dígitos, esos
    dígitos dentro de la matrícula), ordenados por código. Sin `query`,
    los primeros `limit` por código.
    """
    qs = MachineAsset.objects.filter(company=company, is_active=True)
    query = (query or "").strip()
    if query:
        digits = "".join(ch for ch in query if ch.isdigit())
        plate_filter = Q(plate__icontains=query)
        if len(digits) >= _MIN_PLATE_DIGITS:
            plate_filter |= Q(plate__icontains=digits)
        qs = qs.filter(
            Q(code__icontains=query)
            | Q(brand_model__icontains=query)
            | plate_filter
        )
    return qs.order_by("code")[:limit]


def resolve_cost_center(company, code):
    """
    The active cost centre with exactly that code (case-insensitive), or
    None. Accepts the "CODE — brand/model" label the picker writes.
    ---
    El centro de gasto activo con exactamente ese código (sin distinguir
    mayúsculas), o None. Acepta también la etiqueta "CÓDIGO — marca/
    modelo" que escribe el desplegable al elegir.
    """
    code = (code or "").split(" — ")[0].strip()
    if not code:
        return None
    return MachineAsset.objects.filter(
        company=company, is_active=True, code__iexact=code,
    ).first()
