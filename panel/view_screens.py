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
    "personal": "Personal",
    "refuels": "Repostajes",
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
    "workshop_tickets_list": "Taller: tickets de avería",
    "workshop_reviews": "Taller: revisiones",
    "workshop_logbooks": "Taller: libros historial",
    "work_orders": "Partes digitales",
}
