# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/access_profiles.py
"""
The access profiles agreed with Miguel Ángel (S163, 26/11/2026).

---

Los perfiles de acceso acordados con Miguel Ángel (S163, 26/11/2026),
como datos: qué áreas del panel abre cada rol («panel.<área>» en
Permisos), los accesos propios de algunas personas y los cambios de rol
que acompañan al encendido de la puerta por áreas. Los aplica el
comando `apply_access_profiles`; después se cambian desde Permisos.

- Base (todos): su perfil, Mis solicitudes, Mi buzón, Vacaciones y
  Repuestos (subir albaranes; el resto de Repuestos lo siguen guardando
  sus reglas).
- Mecánicos: la base, sus partes, Partes de trabajo, el chat de averías
  e Historial (el almacén va por sus reglas dentro de Repuestos).
- Oficina (rol de Yolanda, renombrado): Empresa/Documentación, Centros
  de gasto y Personal completos («Ver y modificar») salvo Nóminas,
  Firmas y Seguros, que siguen siendo de quien tiene la llave; cierre de
  periodos incluido (Partes de trabajo).
- Supervisor (solo Jerónimo): todo el panel con las reglas de siempre.
- Asistencia: la base y Asistencia con las reglas de siempre.
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

# "*" = toda la sección «Panel actual» (cada pantalla con sus reglas).
ROLE_AREAS = {
    "ADMIN": {"*": VIEW},
    "SUPERVISOR": {"*": VIEW},
    "DOCS_SUPERVISOR": OFFICE,
    "WORKSHOP": WORKSHOP,
    "ASSISTANCE": ASSISTANCE,
    "ASSIST_SUPERVISOR": ASSISTANCE,
    "DRIVER": BASE,
    "CRANE_OPERATOR": BASE,
    "OFFICE": BASE,
    "SALES": BASE,
    "SERVICES": BASE,
    "NIGHTGUARD": BASE,
}

# Accesos propios: (pk de CompanyUser, usuario) -> {área: nivel}.
USER_AREAS = {
    # José Luis (Pepe): Asistencia como hasta ahora (era Administrador).
    (23, "Pepe.Alvarez"): {"asistencia": EDIT},
}

# Cambios de rol del encendido: (pk, usuario) -> rol nuevo.
OFFICE_ROLE = "DOCS_SUPERVISOR"
ROLE_CHANGES = {
    (21, "Carolina"): OFFICE_ROLE,
    (7, "MARIA"): OFFICE_ROLE,
    (65, "carlos.nunez"): OFFICE_ROLE,
    (85, "josecarlos.contreras"): OFFICE_ROLE,
    (6, "rocio.macias"): OFFICE_ROLE,
    (20, "Alberto Álvarez"): OFFICE_ROLE,
    (23, "Pepe.Alvarez"): OFFICE_ROLE,
    (43, "carlos.carlin"): OFFICE_ROLE,
    (47, "juan.arrabali"): OFFICE_ROLE,
    (24, "coco.alvarez"): OFFICE_ROLE,
}
# Superadministrador: superusuario sin is_staff (no entra al admin de
# Django; CompanyUserAdminBlockMiddleware lo bloquea).
SUPERADMINS = {(4, "alejandro_sergio")}
DEACTIVATE = {(3, "alvarez_staff_01")}

# Nueva interfaz (claves de Permisos): secciones enteras y llaves.
NONE = "NONE"
PAYSLIP_KEYS = ("per.nominas", "doc.nominas", "doc.entregas_nominas")
SIGNATURE_KEYS = ("doc.firmas", "doc.firmas_guardadas",
                  "doc.certificados", "doc.agentes_firma")
INSURANCE_KEYS = ("doc.seguros",)
ROLE_NEW_UI = {
    "DOCS_SUPERVISOR": dict(
        {"doc": EDIT, "per": EDIT, "cdg": EDIT},
        **{key: NONE for key in PAYSLIP_KEYS + SIGNATURE_KEYS
           + INSURANCE_KEYS}),
    "SUPERVISOR": {"doc": EDIT, "per": EDIT, "cdg": EDIT},
}
USER_NEW_UI = {
    # Yolanda: sus llaves de Firmas y Seguros.
    (40, "yolanda.bandera"): {
        key: EDIT for key in SIGNATURE_KEYS + INSURANCE_KEYS},
}
