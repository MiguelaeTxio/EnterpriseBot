# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/access_profiles.py
"""
The access profiles agreed with Miguel Ángel (S163, 26/11/2026).

---

Los perfiles de permisos acordados con Miguel Ángel (S163, 26/11/2026),
como datos. El puesto (rol) de cada persona no se toca: solo dice su
trabajo (fichajes, partes, avisos); lo que puede abrir lo decide su
perfil de permisos (grupo de usuarios en Permisos) y, dentro de cada
área con «Ver», las reglas de su puesto de siempre.

- Trabajador (gruistas, chóferes, guarda, administrativos, comercial,
  servicios y el personal de asistencia que se da de alta para
  fichar): su perfil, Mis solicitudes, Mi buzón, Vacaciones, Subir
  albarán y abrir su albarán de asistencia si conduce una unidad.
- Mecánico: lo mismo, más sus partes, Partes de trabajo, el almacén, el
  chat de averías e Historial.
- Asistencia (Paloma, Daniel, Juan Vázquez, «asistencia», José Luis):
  Asistencia con las reglas de su puesto.
- Oficina: Empresa/Documentación, Centros de gasto y Personal completos
  («Ver y modificar», cierre de periodos incluido), salvo Nóminas,
  Firmas y Seguros, que van por llave personal.
- Supervisor (Jerónimo): todo el panel con las reglas de siempre y toda
  la nueva interfaz.
Lo aplica `apply_access_profiles`; después se cambia desde Permisos.
"""

VIEW = "VIEW"
EDIT = "EDIT"

BASE = {
    "mi-perfil": VIEW,
    "mis-solicitudes": VIEW,
    "mi-buzon": VIEW,
    "vacaciones": VIEW,
    "repuestos": VIEW,
}

WORKSHOP = dict(BASE, **{
    # Asistencia «Ver»: por si conduce una unidad (abre su albarán).
    "asistencia": VIEW,
    "mis-partes": VIEW,
    "partes-de-trabajo": VIEW,
    "chat-y-averias": VIEW,
    "historial": VIEW,
})

OFFICE_DOC_FULL = (
    "doc-accesorios", "doc-avisos", "doc-bandeja", "doc-calendario",
    "doc-cae", "doc-circulares", "doc-dosieres", "doc-epis", "doc-equipos",
    "doc-especificaciones", "doc-fichajes", "doc-general", "doc-horarios",
    "doc-maquinaria", "doc-pedir", "doc-personal", "doc-plantillas",
    "doc-puestos", "doc-repostajes", "doc-revisiones", "doc-solicitudes",
    "doc-vacaciones",
)
OFFICE = dict(BASE, **{key: EDIT for key in OFFICE_DOC_FULL}, **{
    # Llaves: entra, pero manda el acceso propio de cada persona.
    "doc-nominas": VIEW,
    "doc-firmas": VIEW,
    "doc-seguros": VIEW,
    "centros-de-gasto": EDIT,
    "gruas": EDIT,
    "obras": EDIT,
    "partes-de-trabajo": EDIT,
    "ausencias": EDIT,
    "tipos-de-ausencia": EDIT,
    "horarios": EDIT,
    "solicitudes": EDIT,
    "vacaciones": EDIT,
    "explorador-de-archivos": VIEW,
    "historial": VIEW,
    "taller": VIEW,
})

ASSISTANCE = dict(BASE, **{"asistencia": VIEW})
# Trabajador: la base y Asistencia («Ver»), para que el conductor de una
# unidad abra su albarán desde el aviso; el resto de Asistencia lo
# siguen guardando las reglas de su puesto.
WORKER = dict(BASE, **{"asistencia": VIEW})

NONE = "NONE"
PAYSLIP_KEYS = ("doc.nominas", "doc.entregas_nominas")
SIGNATURE_KEYS = ("doc.firmas", "doc.firmas_guardadas",
                  "doc.certificados", "doc.agentes_firma")
INSURANCE_KEYS = ("doc.seguros",)
OFFICE_NEW_UI = dict(
    {"doc": EDIT, "per": EDIT, "cdg": EDIT},
    **{key: NONE for key in PAYSLIP_KEYS + SIGNATURE_KEYS
       + INSURANCE_KEYS})

# Perfiles de permisos (grupos de usuarios de Permisos). Cada uno:
# áreas del panel («*» = todo el panel con sus reglas), claves de la
# nueva interfaz, puestos que lo toman por defecto (quien no está en
# ningún perfil) y personas que se meten a mano: (pk, usuario).
PROFILES = {
    "Trabajador": {
        "areas": WORKER,
        "new_ui": {},
        "default_roles": ["CRANE_OPERATOR", "DRIVER", "NIGHTGUARD",
                          "OFFICE", "SALES", "SERVICES", "ASSISTANCE"],
        "members": [],
    },
    "Mecánico": {
        "areas": WORKSHOP,
        "new_ui": {},
        "default_roles": ["WORKSHOP"],
        "members": [],
    },
    "Asistencia": {
        "areas": ASSISTANCE,
        "new_ui": {},
        "default_roles": ["ASSIST_SUPERVISOR"],
        "members": [(None, "paloma"), (None, "daniel.anaya"),
                    (None, "juan.vazquez"), (None, "asistencia"),
                    (23, "Pepe.Alvarez")],
    },
    "Oficina": {
        "areas": OFFICE,
        "new_ui": OFFICE_NEW_UI,
        "default_roles": ["DOCS_SUPERVISOR", "ADMIN_SUPERVISOR"],
        "members": [
            (40, "yolanda.bandera"), (21, "Carolina"), (7, "MARIA"),
            (65, "carlos.nunez"), (85, "josecarlos.contreras"),
            (6, "rocio.macias"), (20, "Alberto Álvarez"),
            (23, "Pepe.Alvarez"), (43, "carlos.carlin"),
            (47, "juan.arrabali"), (24, "coco.alvarez"),
        ],
    },
    "Supervisor": {
        "areas": {"*": VIEW},
        "new_ui": {"doc": EDIT, "per": EDIT, "cdg": EDIT},
        "default_roles": [],
        "members": [(29, "jeronimo")],
    },
}

# Accesos propios: (pk, usuario) -> {clave: nivel}. Las áreas del
# panel van como «panel.<área>».
USER_GRANTS = {
    # José Luis (Pepe): Asistencia como hasta ahora (era Administrador).
    (23, "Pepe.Alvarez"): {"panel.asistencia": EDIT},
    # Yolanda: sus llaves de Firmas y Seguros.
    (40, "yolanda.bandera"): {
        key: EDIT for key in SIGNATURE_KEYS + INSURANCE_KEYS},
}

# Superadministrador: superusuario sin is_staff (no entra al admin de
# Django; CompanyUserAdminBlockMiddleware lo bloquea).
SUPERADMINS = {(4, "alejandro_sergio")}
DEACTIVATE = {(3, "alvarez_staff_01")}
