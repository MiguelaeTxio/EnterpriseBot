# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/catalog.py
"""
Catalogue of the new interface's views (sections and their lists).

---

Catálogo de las vistas de la nueva interfaz (S163, sesión invasora de
UX): una vista única de Documentación con un selector de qué se
gestiona (Documentos, Personal, Centros de gasto, Permisos) y, dentro,
los listados de cada uno en pestañas. Miguel Ángel: "Quiero que
tengamos una única vista para la entrada de documentación que lo
unifique todo".

Cada sección y cada listado tiene una clave (`cdg`, `cdg.documentos`...)
sobre la que se dan permisos (new_ui/permissions.py). Las claves
no se renombran nunca: son las que quedan guardadas en UiViewGrant.
"""
from collections import OrderedDict

PERMISSIONS = "permisos"

# Sección -> (texto, icono, [(clave del listado, texto)]). El orden es
# el del selector y el de las pestañas.
#
# "Ficha" (S163) no es un listado: es la ficha de la persona o máquina
# que se está viendo sola, en la misma vista y con el mismo formato
# que el resto (Miguel Ángel: "que no vaya por acordeones, que siga el
# mismo formato que ya tenemos para todo"). Con una persona o máquina
# sola, "Ficha" ocupa el sitio de "General"; sin ella, no se ve.
FICHA = "ficha"
# Pestañas de una sola persona o máquina (no son listados): solo se ven
# con ella elegida. "QR" (S163): la página del QR del centro de gasto.
ENTITY_TABS = {"per": ("ficha", "jornadas", "desglose_vacaciones"),
               "cdg": ("ficha", "qr")}
# S163 (Miguel Ángel, 23/11: "¿qué es una fila?"): cómo se llama lo que
# hay en cada listado, para que el panel Acciones diga «Con los 3
# trabajadores seleccionados» o «Con el DNI de...», nunca «fila».
TAB_NOUNS = {
    "per": {
        "general": ("trabajador", "trabajadores"),
        "documentos": ("documento", "documentos"),
        "laboral": ("documento", "documentos"),
        "partes": ("parte", "partes"),
        "fichajes": ("fichaje", "fichajes"),
        "repostajes": ("repostaje", "repostajes"),
        "vacaciones": ("periodo de vacaciones", "periodos de vacaciones"),
        "saldo_vacaciones": ("trabajador", "trabajadores"),
        "salud": ("baja", "bajas"),
        "ausencias": ("ausencia", "ausencias"),
        "solicitudes": ("solicitud", "solicitudes"),
        "horarios": ("trabajador", "trabajadores"),
        "lista_horarios": ("horario", "horarios"),
        "tipos_fichaje": ("tipo de fichaje", "tipos de fichaje"),
        "nominas": ("nómina", "nóminas"),
        "epis": ("entrega de EPI", "entregas de EPI"),
        "catalogo_epis": ("EPI", "EPIs"),
        "requisitos": ("requisito", "requisitos"),
    },
    "cdg": {
        "general": ("centro de gasto", "centros de gasto"),
        "documentos": ("documento", "documentos"),
        "especificaciones": ("centro de gasto", "centros de gasto"),
        "avisos": ("documento", "documentos"),
        "revisiones": ("revisión", "revisiones"),
        "lecturas": ("lectura", "lecturas"),
        "repostajes": ("repostaje", "repostajes"),
        "accesorios": ("accesorio", "accesorios"),
        "taller": ("parte de taller", "partes de taller"),
        "averias": ("avería", "averías"),
        "libro": ("anotación del libro", "anotaciones del libro"),
        "equipos": ("equipo", "equipos"),
    },
}

SECTIONS = OrderedDict([
    ("doc", ("Documentos", "bi-folder2-open", [
        ("bandeja", "Bandeja de entrada"),
        ("circulares", "Circulares"),
        ("plantillas_circular", "Plantillas de circular"),
        ("dosieres", "Dosieres"),
        ("lista_requisitos", "Requisitos"),
        ("avisos", "Avisos"),
        ("pedir", "Pedir documentos"),
        ("firmas", "Firmas"),
        ("seguros", "Seguros"),
        ("calendario", "Calendario"),
    ])),
    ("per", ("Personal", "bi-people", [
        ("general", "General"),
        ("ficha", "Ficha"),
        ("documentos", "Documentos"),
        ("laboral", "Laboral"),
        ("partes", "Partes"),
        ("fichajes", "Fichajes"),
        ("jornadas", "Jornadas"),
        ("alta_fichaje", "Alta en el fichaje"),
        ("repostajes", "Repostajes"),
        ("vacaciones", "Vacaciones"),
        ("saldo_vacaciones", "Saldo de vacaciones"),
        ("desglose_vacaciones", "Desglose de vacaciones"),
        ("salud", "Salud"),
        ("ausencias", "Ausencias"),
        ("solicitudes", "Solicitudes"),
        ("horarios", "Horarios"),
        ("lista_horarios", "Lista de horarios"),
        ("tipos_fichaje", "Tipos de fichaje"),
        ("nominas", "Nóminas"),
        ("epis", "EPIs"),
        ("catalogo_epis", "Catálogo de EPIs"),
        ("requisitos", "Requisitos"),
    ])),
    ("cdg", ("Centros de gasto", "bi-truck", [
        ("general", "General"),
        ("ficha", "Ficha"),
        ("qr", "QR"),
        ("documentos", "Documentos"),
        ("especificaciones", "Especificaciones"),
        ("avisos", "Avisos"),
        ("revisiones", "Revisiones"),
        ("lecturas", "Lecturas"),
        ("repostajes", "Repostajes"),
        ("accesorios", "Accesorios"),
        ("taller", "Taller"),
        ("averias", "Averías"),
        ("libro", "Libro historial"),
        ("equipos", "Equipos"),
    ])),
    (PERMISSIONS, ("Permisos", "bi-shield-lock", [
        ("usuarios", "Usuarios"),
        ("grupos", "Grupos de usuarios"),
        ("vistas", "Por vista"),
    ])),
])


def section_key(view_key):
    """
    "cdg.documentos" -> "cdg".

    ---

    La sección a la que pertenece una clave.
    """
    return view_key.split(".", 1)[0]


def all_view_keys():
    """
    [(key, label, depth)] of every grantable view, in display order.

    ---

    Todas las vistas a las que se dan permisos, en orden: la sección
    (profundidad 0) y debajo sus listados (profundidad 1). Permisos no
    entra: de momento solo la ve el superusuario, sin permisos que dar.
    """
    rows = []
    for key, (label, _icon, tabs) in SECTIONS.items():
        if key == PERMISSIONS:
            continue
        rows.append((key, label, 0))
        for tab_key, tab_label in tabs:
            rows.append(("%s.%s" % (key, tab_key), tab_label, 1))
    return rows


def label_of(view_key):
    """
    "Centros de gasto › Documentos" for a key; the key if unknown.

    ---

    Rótulo legible de una clave.
    """
    section = section_key(view_key)
    if section not in SECTIONS:
        return view_key
    label, _icon, tabs = SECTIONS[section]
    if view_key == section:
        return label
    tab = view_key.split(".", 1)[1]
    return "%s › %s" % (label, dict(tabs).get(tab, tab))
