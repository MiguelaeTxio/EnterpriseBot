# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/view_screens.py
"""
Panel lists whose columns are configured from their own table (S153).

---

Listados del panel sin catálogo de exportación cuyas columnas se
configuran a partir de su propia tabla (S153, pestaña "Columnas"): la
cabecera marca cada columna con data-col y el navegador oculta y
reordena las celdas (panel/_view_columns_tab.html). Aquí solo se da de
alta cada pantalla (clave y nombre) para guardar sus plantillas y lo
que ve cada usuario.
"""

VIEW_SCREENS = {
    "worker_requests": "Solicitudes",
    "clock_events": "Fichajes",
    "crews_list": "Equipos",
    "epi_deliveries": "EPIs",
    "lifting_accessories": "Accesorios de elevación",
    "vacation_balance": "Vacaciones",
    "worker_schedules": "Horarios",
    "payslips_list": "Nóminas",
    "doc_requests": "Pedir documentos",
    "signatures_documentos": "Firmas: documentos firmados",
    "signatures_firmas": "Firmas: firmas",
    "signatures_certificados": "Firmas: certificados",
    "signatures_agentes": "Firmas: agentes",
    "insurance": "Seguros",
    "inbox": "Bandeja",
    "users": "Usuarios",
    "telephony_lists": "Telefonía",
    "db_backups": "Copias de la base de datos",
    "workshop_tasks_list": "Taller: tareas",
    # S157: las otras vistas de Repostajes (Ver: Vehículos, Repostadores,
    # Preguntas); la de repostajes tiene catálogo (screen_export_catalog).
    "refuels_vehicles": "Repostajes: vehículos",
    "refuels_users": "Repostajes: repostadores",
    "refuels_questions": "Repostajes: preguntas",
    "workshop_tickets_list": "Taller: tickets de avería",
    "workshop_reviews": "Taller: revisiones",
    "workshop_logbooks": "Taller: libros historial",
    "work_orders": "Partes digitales",
    # H11 (S162): página Grúas.
    "crane_albaranes_list": "Grúas: albaranes",
    "crane_worksites_list": "Grúas: obras",
    "crane_clients_list": "Grúas: clientes",
}

# S153 (Miguel Ángel: "la vista del panel, que sea la que se elige por
# defecto, sea exactamente la vista que esté seleccionada en ese momento
# en el panel"). Para cada exportación con catálogo propio: el listado
# del panel del que toma la "Vista del panel", las columnas de la
# exportación que van siempre delante (las fijas del listado) y qué
# columnas de la exportación corresponden a cada columna del listado.
EXPORT_VIEWS = {
    "personal": {
        "view": "personal",
        "fixed": ["apellidos_nombre"],
        "map": {
            "dni": ["dni"], "hire_date": ["fecha_alta"],
            "doc_count": ["documentos"],
            "requirement": ["requisito", "estado_requisito"],
            "onboarding": ["alta_fichaje"], "section": ["seccion"],
            "schedule": ["horario"],
            # S157: las columnas de la exportación que se pueden ver
            # en el listado llevan la misma clave en los dos.
            **{key: [key] for key in (
                "primer_apellido", "segundo_apellido", "nombre",
                "fecha_nacimiento", "empresa", "estado", "fecha_baja",
                "categoria", "estado_requisito", "telefono", "telefono_2",
                "contacto_emergencia", "telefono_emergencia", "email",
                "direccion", "codigo_postal", "poblacion", "provincia",
                "num_ss", "cad_dni", "cad_carnet", "cad_gruista", "cad_cap",
                "cad_tacografo", "reconocimiento", "usuario_panel")},
        },
    },
    "refuels": {
        "view": "refuels",
        "fixed": ["fecha", "hora"],
        "map": {
            "machine": ["centro"], "vehicle": ["matricula"],
            "driver": ["quien"], "value": ["km"], "litres": ["litros"],
            "status": ["estado"], "unit": ["unidad"], "reason": ["motivo"],
            # S157: las que antes solo salían al exportar.
            "plate": ["matricula"], "name": ["nombre"],
            "price": ["precio"], "hours": ["horas"],
        },
    },
    "crews": {
        "view": "crews_list",
        "fixed": [],
        "map": {
            "code": ["codigo"], "machine": ["centro"],
            "plate": ["matricula"], "person": ["persona"],
            "phone": ["telefono", "telefono_emergencia"],
            "start": ["desde"], "end": ["hasta"],
        },
    },
    "payslips": {
        "view": "payslips_list",
        "fixed": [],
        "map": {
            "batch": ["entrega", "subida"], "file": ["archivo"],
            "pages": ["paginas"], "person": ["trabajador"], "dni": ["dni"],
            "month": ["mes"], "phone": ["movil"], "status": ["estado"],
            "sent": ["enviada"], "note": ["nota"],
        },
    },
    "workshop_tasks": {
        "view": "workshop_tasks_list",
        "fixed": [],
        "map": {
            "fecha": ["fecha"], "mecanico": ["mecanico"], "tipo": ["tipo"],
            "averia_tarea": ["descripcion"], "horario": ["horario"],
            "jornada": ["jornada"], "h_ordinarias": ["h_ordinarias"],
            "h_extra": ["h_extra"], "h_festivas": ["h_festivas"],
            "horas": ["horas"], "repuestos": ["repuestos"],
            "importe": ["importe"], "albaranes": ["albaranes"],
            "ticket": ["ticket"],
        },
    },
    "workshop_tickets": {
        "view": "workshop_tickets_list",
        "fixed": [],
        "map": {key: [key] for key in (
            "ticket", "fecha", "estado", "urgencia", "tipo", "averia",
            "tareas", "h_ordinarias", "h_extra", "h_festivas", "horas",
            "importe", "cerrada")},
    },
    # H11 (S162): página Grúas.
    "crane_albaranes": {
        "view": "crane_albaranes_list",
        "fixed": [],
        "map": {
            "number": ["numero"], "day": ["fecha"], "time": ["hora"],
            "person": ["gruista"], "worksite": ["obra"],
            "client": ["cliente"], "machine": ["maquina"],
            "hours": ["horas"], "status": ["estado"],
            "delivery": ["entregado"],
        },
    },
    "crane_worksites": {
        "view": "crane_worksites_list",
        "fixed": [],
        "map": {
            "code": ["codigo"], "name": ["obra"], "client": ["cliente"],
            "project": ["proyecto"], "place": ["ubicacion"],
            "contact": ["contacto"], "delivery": ["entrega"],
            "albaranes": ["albaranes"],
        },
    },
    "crane_clients": {
        "view": "crane_clients_list",
        "fixed": [],
        "map": {
            "name": ["cliente"], "tax_id": ["nif"], "place": ["localidad"],
            "phone": ["telefono"], "email": ["correo"], "sites": ["obras"],
        },
    },
}
