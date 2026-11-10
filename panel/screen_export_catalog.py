# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/screen_export_catalog.py
"""
Column catalogues of the exportable screens (S148).

---

Catálogos de columnas de las pantallas con plantillas de exportación
comunes (panel/screen_exports.py). Cada pantalla: todas las columnas
que se pueden elegir y, en `panel_columns`, las de su tabla en el
panel, que forman la plantilla fija "Vista del panel".
"""
from panel.screen_exports import Column, Screen, register

DATE = "DD/MM/YYYY"


def _counters(asset):
    names = []
    if asset.has_odometer:
        names.append("Km")
    if asset.has_engine_hours:
        names.append("Horas motor")
    if asset.has_crane_hours:
        names.append("Horas grúa")
    return ", ".join(names)


def _short_company(asset):
    from fleet.views import _short_company_name

    return _short_company_name(asset.company_name)


# Centros de gasto. Los objetos son MachineAsset con doc_count y
# use_count puestos por la exportación (fleet.views).
FLEET = register(Screen(
    key="fleet",
    label="Centros de gasto",
    columns=(
        Column("codigo", "Código", 12, lambda a: a.code),
        Column("familia", "Familia", 16, lambda a: a.family),
        Column("descripcion", "Descripción", 34, lambda a: a.brand_model),
        Column("tipo", "Tipo", 26, lambda a: a.type_name),
        Column("matricula", "Matrícula", 14, lambda a: a.plate),
        Column("documentos", "Documentos", 11,
               lambda a: getattr(a, "doc_count", None), summed=True),
        Column("contadores", "Contadores", 22, _counters),
        Column("requisito", "Requisito de documentación", 26,
               lambda a: (a.document_requirement.name
                          if a.document_requirement_id else "")),
        Column("estado", "Estado", 10,
               lambda a: "Activo" if a.is_active else "Inactivo"),
        Column("usos", "Usos (líneas de parte)", 12,
               lambda a: getattr(a, "use_count", None), summed=True),
        Column("bastidor", "Nº de bastidor", 20,
               lambda a: a.chassis_number),
        Column("fecha_compra", "Fecha de compra", 12,
               lambda a: a.purchase_date, DATE),
        Column("km", "Km", 10, lambda a: a.mileage),
        Column("horas", "Horas", 10, lambda a: a.hours),
        Column("itv", "ITV", 12, lambda a: a.itv_date, DATE),
        Column("cita_itv", "Cita ITV", 12,
               lambda a: a.itv_next_appointment, DATE),
        Column("seguro", "Seguro", 24, lambda a: a.insurance_info),
        Column("oca", "OCA", 12, lambda a: a.oca_date, DATE),
        Column("empresa", "Empresa", 28, _short_company),
        Column("codigo_empresa", "Código de empresa", 10,
               lambda a: a.company_code),
        Column("observaciones", "Observaciones", 40, lambda a: a.notes),
    ),
    panel_columns=[
        "codigo", "familia", "descripcion", "tipo", "matricula",
        "documentos", "contadores", "requisito", "estado", "usos",
    ],
))
