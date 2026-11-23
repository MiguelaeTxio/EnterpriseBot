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
        "comunicaciones": ("trabajador", "trabajadores"),
        "pedidos": ("petición", "peticiones", "f"),
        "circulares_rec": ("circular", "circulares", "f"),
        "bajas": ("trabajador", "trabajadores"),
        "partes_trab": ("trabajador", "trabajadores"),
        "repostajes_trab": ("trabajador", "trabajadores"),
        "epis_trab": ("trabajador", "trabajadores"),
        "documentos": ("documento", "documentos"),
        "laboral": ("documento", "documentos"),
        "partes": ("parte", "partes"),
        "fichajes": ("fichaje", "fichajes"),
        "repostajes": ("repostaje", "repostajes"),
        "vacaciones": ("periodo de vacaciones", "periodos de vacaciones"),
        "saldo_vacaciones": ("trabajador", "trabajadores"),
        "salud": ("baja", "bajas", "f"),
        "ausencias": ("ausencia", "ausencias", "f"),
        "solicitudes": ("solicitud", "solicitudes", "f"),
        "horarios": ("trabajador", "trabajadores"),
        "nominas": ("nómina", "nóminas", "f"),
        "epis": ("entrega de EPI", "entregas de EPI", "f"),
        "requisitos": ("trabajador", "trabajadores"),
    },
    "doc": {
        "bandeja": ("documento", "documentos"),
        "circulares": ("circular", "circulares", "f"),
        "plantillas_circular": ("plantilla", "plantillas", "f"),
        "dosieres": ("dosier", "dosieres"),
        "lista_requisitos": ("requisito", "requisitos"),
        "avisos": ("aviso", "avisos"),
        "pedir": ("trabajador", "trabajadores"),
        "firmas": ("documento", "documentos"),
        "seguros": ("informe", "informes"),
        "nominas": ("nómina", "nóminas", "f"),
        "lista_horarios": ("horario", "horarios"),
        "tipos_fichaje": ("tipo de fichaje", "tipos de fichaje"),
        "catalogo_epis": ("EPI", "EPIs"),
    },
    "cdg": {
        "general": ("centro de gasto", "centros de gasto"),
        "documentos": ("documento", "documentos"),
        "especificaciones": ("centro de gasto", "centros de gasto"),
        "avisos": ("documento", "documentos"),
        "revisiones": ("revisión", "revisiones", "f"),
        "lecturas": ("lectura", "lecturas", "f"),
        "repostajes": ("repostaje", "repostajes"),
        "accesorios": ("accesorio", "accesorios"),
        "taller": ("parte de taller", "partes de taller"),
        "averias": ("avería", "averías", "f"),
        "libro": ("anotación del libro", "anotaciones del libro", "f"),
        "equipos": ("equipo", "equipos"),
    },
}

# S163 (Miguel Ángel, 23/11): las vistas de cada sección, agrupadas en un
# nivel más (Personal › Fichaje › Tipos de fichaje), para que la hilera
# de arriba quepa en una línea y cada grupo junte lo suyo. Solo cambia
# cómo se enseñan: las claves de cada vista (y sus permisos) no cambian.
# Una vista que no esté en ningún grupo va sola, con su nombre.
TAB_GROUPS = {
    "doc": [
        ("Documentación", ("lista_requisitos", "avisos", "dosieres")),
        ("Circulares", ("plantillas_circular", "circulares")),
        ("Firmas", ("firmas",)),
        ("Seguros", ("seguros",)),
        ("Fichaje", ("tipos_fichaje", "lista_horarios")),
        ("Vacaciones", ("vacaciones",)),
        ("EPIs", ("catalogo_epis",)),
        ("Nóminas", ("nominas",)),
    ],
    # Personal (23/11): cada tema, su lista de trabajadores (para muchos)
    # y lo de uno solo, en su ficha (VIEW_MODES).
    "per": [
        ("General", ("general", "ficha")),
        ("Documentación", ("requisitos", "documentos", "laboral",
                           "solicitudes")),
        ("Comunicaciones", ("comunicaciones", "pedidos", "circulares_rec")),
        ("Fichaje", ("horarios", "fichajes", "jornadas")),
        ("Vacaciones", ("saldo_vacaciones", "desglose_vacaciones")),
        ("Bajas y ausencias", ("bajas", "salud", "ausencias")),
        ("Partes", ("partes_trab", "partes")),
        ("Repostajes", ("repostajes_trab", "repostajes")),
        ("EPIs", ("epis_trab", "epis")),
    ],
}
# S163 (23/11): la lista de todos («all», sin persona abierta) o lo de
# uno solo («one», con su ficha abierta). Una vista que no está en
# ninguno de los dos se ve siempre. Al pulsar un trabajador se pasa a
# su ficha, en el mismo tema.
VIEW_MODES = {
    "per": {
        "all": ("general", "requisitos", "comunicaciones", "horarios",
                "saldo_vacaciones", "bajas", "partes_trab",
                "repostajes_trab", "epis_trab"),
        "one": ("ficha", "documentos", "laboral", "solicitudes",
                "pedidos", "circulares_rec",
                "fichajes", "jornadas", "desglose_vacaciones", "salud",
                "ausencias", "partes", "repostajes", "epis"),
    },
}


def view_mode(section, key):
    """
    "all", "one" or "" (always shown) for a view of a section.

    ---

    Si una vista es de la lista de todos, de uno solo o de las dos.
    """
    modes = VIEW_MODES.get(section)
    if modes:
        for mode in ("all", "one"):
            if key in modes[mode]:
                return mode
        return ""
    if key in ENTITY_TABS.get(section, ()):
        return "one"
    if key == "general" and ENTITY_TABS.get(section):
        return "all"
    return ""


# S163 (Miguel Ángel, 23/11): lo que se configura para toda la empresa
# (horarios, tipos de fichaje, catálogo de EPIs) pasa de Personal a
# Empresa (la antigua sección Documentos); en Personal queda a quién se
# asigna. Las claves antiguas de sus permisos pasan a las nuevas
# (migración new_ui 0002).
MOVED_VIEWS = {
    "per.lista_horarios": "doc.lista_horarios",
    "per.tipos_fichaje": "doc.tipos_fichaje",
    "per.catalogo_epis": "doc.catalogo_epis",
    "per.nominas": "doc.nominas",
}


def view_groups(section, tabs):
    """
    [(label, [(key, label)])] grouping the given tabs of a section.

    ---

    Las vistas de una sección agrupadas según TAB_GROUPS, en el orden
    de los grupos; las que no estén en ninguno van solas al final.
    """
    by_key = OrderedDict(tabs)
    out = []
    used = set()
    for label, keys in TAB_GROUPS.get(section, []):
        members = [(k, by_key[k]) for k in keys if k in by_key]
        if members:
            out.append((label, members))
            used.update(k for k, _ in members)
    for key, label in by_key.items():
        if key not in used:
            out.append((label, [(key, label)]))
    return out


SECTIONS = OrderedDict([
    # S163 (23/11): «Documentos» pasa a llamarse «Empresa» (gestión de
    # toda la empresa); la clave "doc" no cambia.
    ("doc", ("Empresa", "bi-building", [
        ("lista_requisitos", "Requisitos"),
        ("avisos", "Avisos"),
        ("dosieres", "Dosieres"),
        ("plantillas_circular", "Plantillas"),
        ("circulares", "Enviadas"),
        ("firmas", "Firmas"),
        ("seguros", "Seguros"),
        ("tipos_fichaje", "Tipos de fichaje"),
        ("lista_horarios", "Horarios"),
        ("vacaciones", "Vacaciones"),
        ("catalogo_epis", "Catálogo de EPIs"),
        ("nominas", "Nóminas"),
    ])),
    # S163 (23/11): por temas (TAB_GROUPS); el nombre de la lista de
    # todos es el del tema, y los de la ficha, lo suyo.
    ("per", ("Personal", "bi-people", [
        ("general", "General"),
        ("ficha", "Datos"),
        ("requisitos", "Documentación"),
        ("documentos", "Documentos"),
        ("laboral", "Laboral"),
        ("solicitudes", "Solicitudes"),
        ("comunicaciones", "Comunicaciones"),
        ("pedidos", "Documentos pedidos"),
        ("circulares_rec", "Circulares recibidas"),
        ("horarios", "Fichaje"),
        ("fichajes", "Fichajes"),
        ("jornadas", "Calendario"),
        ("saldo_vacaciones", "Vacaciones"),
        ("desglose_vacaciones", "Desglose"),
        ("bajas", "Bajas y ausencias"),
        ("salud", "Bajas"),
        ("ausencias", "Ausencias"),
        ("partes_trab", "Partes"),
        ("partes", "Partes"),
        ("repostajes_trab", "Repostajes"),
        ("repostajes", "Repostajes"),
        ("epis_trab", "EPIs"),
        ("epis", "Entregas"),
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
