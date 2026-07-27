# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/main.py
"""Entry point of the H28 migration agent (Windows tray app).
---
Punto de entrada del agente de migracion H28 (app de bandeja de
Windows).

Fase 1 punto 1 (anexo H28): la seleccion de carpetas es dinamica,
elegida desde esta interfaz en el momento de usarla — nunca una
lista fija en configuracion. Cada carpeta elegida se copia siempre
de forma recursiva y completa (decision verbatim de Miguel Angel,
S031).
---
Phase 1 point 1 (H28 annex): folder selection is dynamic, chosen
from this interface at the moment of use — never a fixed list in
configuration. Every chosen folder is always copied recursively and
completely (Miguel Angel's verbatim decision, S031).
"""

import logging
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from auditor import (
    audit_folder,
    build_audit_output_path,
    build_summary_text,
    write_summary,
)
from config import DIRTY_BUCKET_NAME, LOG_FILE_NAME
from gcs_client import MissingCredentialsError, build_client
from history import append_event, load_events
from reconciler import reconcile_folder
from state import load_watched_folders, save_watched_folders
from uploader import upload_folder_recursive
from watcher import start_watching

logger = logging.getLogger(__name__)

# Folders being watched in this run, keyed by local path. Persisted
# to disk (state.py) so the agent resumes them automatically on the
# next restart — decision from Miguel Angel, S031.
# ---
# Carpetas vigiladas en esta ejecucion, indexadas por ruta local.
# Se persisten en disco (state.py) para que el agente las retome
# automaticamente en el siguiente reinicio — decision de Miguel
# Angel, S031.
_active_observers = {}


def _configure_logging():
    """Configure file logging, and console logging when available.
    ---
    Configura el log de archivo, y el de consola cuando esta
    disponible.

    Nota (S031): empaquetado con PyInstaller --windowed no da
    consola a la app — sys.stdout/sys.stderr quedan en None. Anadir
    un StreamHandler en ese caso hace petar el primer log.write().
    Se comprueba antes de anadirlo.
    ---
    Note (S031): PyInstaller --windowed packaging gives the app no
    console — sys.stdout/sys.stderr are None. Adding a
    StreamHandler in that case crashes on the first log.write().
    Checked before adding it.
    """
    log_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.argv[0])), LOG_FILE_NAME
    )
    handlers = [logging.FileHandler(log_path, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _build_tray_image():
    """Build a simple placeholder tray icon image.
    ---
    Construye una imagen de icono de bandeja de marcador de
    posicion.

    Nota (S031): icono provisional generado por codigo — pendiente
    de que Miguel Angel entregue un icono .ico definitivo para
    sustituirlo antes de empaquetar con PyInstaller.
    """
    image = Image.new("RGB", (64, 64), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), fill="#2b6cb0")
    draw.text((18, 24), "H28", fill="white")
    return image


def _run_reconciliation(icon, client, selected_folder):
    """Run reconciliation on selected_folder and notify the result.
    ---
    Ejecuta la reconciliacion sobre selected_folder y notifica el
    resultado.

    Shared by the automatic run right after a copy and by the manual
    "Verificar y reparar carpeta" menu item (S033).
    ---
    Compartida por la ejecucion automatica justo tras una copia y
    por el item de menu manual "Verificar y reparar carpeta" (S033).
    """
    logger.info("Inicio de reconciliacion: %s", selected_folder)

    def _log_reconcile_progress(checked_count, total_count):
        logger.info(
            "Progreso reconciliacion %s: %d/%d",
            selected_folder, checked_count, total_count,
        )

    repaired_count, skipped_in_quarantine_count, unrecoverable_paths = (
        reconcile_folder(
            client, DIRTY_BUCKET_NAME, selected_folder,
            _log_reconcile_progress,
        )
    )

    if not repaired_count and not skipped_in_quarantine_count \
            and not unrecoverable_paths:
        summary = "Todo correcto, sin huecos"
    elif unrecoverable_paths:
        summary = (
            f"{repaired_count} reparado(s), "
            f"{skipped_in_quarantine_count} ya en cuarentena, "
            f"{len(unrecoverable_paths)} irrecuperable(s)"
        )
    else:
        summary = (
            f"{repaired_count} reparado(s), "
            f"{skipped_in_quarantine_count} ya en cuarentena"
        )

    if unrecoverable_paths:
        icon.notify(
            f"Reconciliacion: {summary}. Ver el log para el "
            "detalle.",
            title="Agente H28",
        )
    else:
        icon.notify(f"Reconciliacion: {summary}.", title="Agente H28")

    append_event("Reconciliacion", selected_folder, summary)


def _verify_and_repair_folder(icon, _menu_item):
    """Let Miguel Angel pick a folder and reconcile it on demand.
    ---
    Permite a Miguel Angel elegir una carpeta y reconciliarla bajo
    demanda.

    S033: cubre la verificacion/reparacion de cualquier carpeta ya
    migrada (o nueva) sin salir del agente ni tocar ninguna consola.
    ---
    S033: covers verifying/repairing any already-migrated (or new)
    folder without leaving the agent or touching any console.
    """
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta a verificar y reparar (H28)",
        parent=root,
    )
    root.destroy()

    if not selected_folder:
        return
    selected_folder = os.path.normpath(selected_folder)

    try:
        client = build_client()
    except MissingCredentialsError as error:
        messagebox.showerror("Agente H28", str(error))
        return

    icon.notify(
        f"Verificando {selected_folder}...", title="Agente H28",
    )
    _run_reconciliation(icon, client, selected_folder)


def _audit_folder(icon, _menu_item):
    """Run the read-only Phase 2 audit over a chosen local folder.
    ---
    Ejecuta la auditoria de solo lectura de la Fase 2 sobre una
    carpeta local elegida.

    S034, decision de Miguel Angel ("podemos integrarlo en el
    agente"): el paso 1 de la Fase 2 se lanza desde aqui, no desde
    una consola. No toca GCS ni la cuenta de servicio -- es
    estrictamente local y estrictamente de lectura, asi que no
    requiere credenciales.
    ---
    S034, Miguel Angel's decision: Phase 2 step 1 is launched from
    here, not from a console. It never touches GCS nor the service
    account -- it is strictly local and strictly read-only, so no
    credentials are required.
    """
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta a auditar (H28 Fase 2)",
        parent=root,
    )
    if not selected_folder:
        root.destroy()
        return
    selected_folder = os.path.normpath(selected_folder)

    confirmed = messagebox.askyesno(
        "Agente H28",
        f"Se va a auditar:\n{selected_folder}\n\n"
        "Se calculará el hash SHA-256 de cada archivo, por lo que "
        "hay que leerlos todos enteros: puede tardar bastantes "
        "minutos y el menú del agente no responderá mientras tanto."
        "\n\nNo se modifica ni se borra nada: la pasada es "
        "exclusivamente de lectura.\n\n¿Continuar?",
        parent=root,
    )
    root.destroy()
    if not confirmed:
        return

    icon.notify(
        f"Auditando {selected_folder}...", title="Agente H28",
    )
    logger.info("Inicio de auditoria: %s", selected_folder)

    def _log_audit_progress(file_count, total_bytes):
        logger.info(
            "Progreso auditoria %s: %d archivos, %d bytes",
            selected_folder, file_count, total_bytes,
        )

    csv_path = build_audit_output_path(selected_folder)
    try:
        stats = audit_folder(
            selected_folder, csv_path, _log_audit_progress,
        )
    except OSError as error:
        logger.error(
            "Auditoria abortada sobre %s: %s", selected_folder, error,
        )
        messagebox.showerror(
            "Agente H28",
            f"No se pudo completar la auditoría:\n{error}",
        )
        append_event("Auditoria", selected_folder, f"Error: {error}")
        return

    summary_text = build_summary_text(
        selected_folder, csv_path, stats,
    )
    summary_path = write_summary(summary_text, csv_path)

    summary = (
        f"{stats['file_count']} archivos, "
        f"{stats['error_count']} errores"
    )
    icon.notify(f"Auditoria terminada: {summary}.", title="Agente H28")
    append_event("Auditoria", selected_folder, summary)

    messagebox.showinfo(
        "Agente H28",
        f"Auditoría completada.\n\n{summary_text}\n\n"
        f"Resumen guardado en:\n{summary_path}",
    )


def _show_history(icon, _menu_item):
    """Open a read-only window listing the agent's recent events.
    ---
    Abre una ventana de solo lectura con los eventos recientes del
    agente.

    S033, decision de Miguel Angel: el visor de tareas vive en el
    propio agente, no en la plataforma web. Muestra los eventos
    guardados por history.py (copias y reconciliaciones), mas
    reciente primero -- sin necesidad de abrir el log.
    ---
    S033, Miguel Angel's decision: the task viewer lives in the
    agent itself, not the web platform. Shows the events stored by
    history.py (copies and reconciliations), most recent first --
    without needing to open the log.
    """
    events = load_events()

    window = tk.Tk()
    window.title("Agente H28 — Historial")
    window.geometry("820x420")
    window.attributes("-topmost", True)

    columns = ("timestamp", "event_type", "folder", "summary")
    headings = {
        "timestamp": "Fecha/hora (UTC)",
        "event_type": "Accion",
        "folder": "Carpeta",
        "summary": "Resultado",
    }
    tree = ttk.Treeview(window, columns=columns, show="headings")
    for column in columns:
        tree.heading(column, text=headings[column])
    tree.column("timestamp", width=160, anchor="w")
    tree.column("event_type", width=120, anchor="w")
    tree.column("folder", width=320, anchor="w")
    tree.column("summary", width=200, anchor="w")

    if not events:
        tree.insert("", "end", values=(
            "", "", "Sin eventos todavia", "",
        ))
    for event in events:
        tree.insert("", "end", values=(
            event.get("timestamp", ""),
            event.get("event_type", ""),
            event.get("folder", ""),
            event.get("summary", ""),
        ))

    scrollbar = ttk.Scrollbar(
        window, orient="vertical", command=tree.yview,
    )
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    window.mainloop()


def _select_folder_and_copy(icon, _menu_item):
    """Open the folder picker, then copy and watch it.
    ---
    Abre el selector de carpetas, y la copia y vigila.
    """
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta a migrar (H28)",
        parent=root,
    )
    root.destroy()

    if not selected_folder:
        return
    selected_folder = os.path.normpath(selected_folder)

    if selected_folder in _active_observers:
        messagebox.showinfo(
            "Agente H28",
            f"Esta carpeta ya se esta vigilando:\n{selected_folder}",
        )
        return

    try:
        client = build_client()
    except MissingCredentialsError as error:
        messagebox.showerror("Agente H28", str(error))
        return

    icon.notify(f"Copiando {selected_folder}...", title="Agente H28")
    logger.info("Inicio de copia inicial: %s", selected_folder)

    def _log_progress(uploaded_count, total_count):
        logger.info(
            "Progreso copia %s: %d/%d",
            selected_folder,
            uploaded_count,
            total_count,
        )

    uploaded_count, failed_paths = upload_folder_recursive(
        client, DIRTY_BUCKET_NAME, selected_folder, _log_progress
    )

    if failed_paths:
        icon.notify(
            f"Copia terminada con {len(failed_paths)} fallos. "
            "Reconciliando automaticamente...",
            title="Agente H28",
        )
        append_event(
            "Copia inicial", selected_folder,
            f"{uploaded_count} subidos, {len(failed_paths)} fallos",
        )
    else:
        icon.notify(
            f"Copia completada: {uploaded_count} archivos. "
            "Verificando integridad...",
            title="Agente H28",
        )
        append_event(
            "Copia inicial", selected_folder,
            f"{uploaded_count} archivos, 0 fallos",
        )

    # Reconciliacion automatica (S033): tras la copia, se vuelve a
    # comparar local vs. cubo y se repara cualquier hueco -- ya sea
    # un fallo de subida o un archivo que el escaneo inicial se
    # salto -- sin intervencion manual por consola.
    # ---
    # Automatic reconciliation (S033): after the copy, local vs.
    # bucket is compared again and any gap is repaired -- whether an
    # upload failure or a file the initial scan missed -- without
    # manual console intervention.
    _run_reconciliation(icon, client, selected_folder)

    observer = start_watching(client, selected_folder)
    _active_observers[selected_folder] = observer
    save_watched_folders(_active_observers.keys())
    icon.notify(
        f"Vigilancia continua activa sobre:\n{selected_folder}",
        title="Agente H28",
    )


def _resume_watched_folders(icon):
    """Resume watching every folder persisted from a previous run.
    ---
    Retoma la vigilancia de cada carpeta persistida de una
    ejecución anterior.

    Called once, right after the tray icon becomes visible (pystray
    ``setup`` callback) — decision from Miguel Ángel (S031): "el
    agente tiene que recordar qué estaba haciendo y seguir
    haciéndolo".

    S034 closes the gap S031 left documented and S033 left pending
    an explicit decision: reconciliation now runs automatically over
    every resumed folder, so files that appeared while the agent was
    closed no longer stay invisible until someone remembers to ask
    for a manual check. Miguel Ángel's decision, verbatim: "creo que
    es lo más lógico de hacerlo de forma automática una vez que
    arranque el agente".
    ---
    S034 cierra el hueco que S031 dejó documentado y S033 dejó
    pendiente de decisión explícita: la reconciliación se ejecuta
    ahora automáticamente sobre cada carpeta retomada, de modo que
    los archivos aparecidos con el agente cerrado dejan de quedar
    invisibles hasta que alguien se acuerde de pedir una
    verificación manual. Decisión de Miguel Ángel, verbatim: "creo
    que es lo más lógico de hacerlo de forma automática una vez que
    arranque el agente".
    """
    # pystray exige que, al sustituir el setup por defecto, este
    # mismo lo deje visible explicitamente -- si no, el icono nunca
    # aparece (verificado en la documentacion oficial de pystray).
    # ---
    # pystray requires that, when the default setup is replaced,
    # this one makes the icon visible itself -- otherwise it never
    # shows (verified against the official pystray documentation).
    icon.visible = True

    persisted_folders = load_watched_folders()
    if not persisted_folders:
        return

    missing_folders = [
        folder for folder in persisted_folders
        if not os.path.isdir(folder)
    ]
    valid_folders = [
        folder for folder in persisted_folders
        if os.path.isdir(folder)
    ]
    for missing_folder in missing_folders:
        logger.warning(
            "Carpeta persistida ya no existe, se descarta: %s",
            missing_folder,
        )

    if not valid_folders:
        save_watched_folders([])
        return

    try:
        client = build_client()
    except MissingCredentialsError as error:
        logger.error(
            "No se pudieron retomar %d carpetas persistidas: %s",
            len(valid_folders),
            error,
        )
        icon.notify(
            "No se pudo retomar la vigilancia de sesiones "
            "anteriores: falta la clave de la cuenta de servicio.",
            title="Agente H28",
        )
        return

    # La vigilancia se arranca ANTES de reconciliar, a propósito: la
    # reconciliación de una carpeta grande tarda minutos, y durante
    # esa ventana los archivos que se creen en local deben llegar
    # igualmente a cuarentena. Al revés se perderían esos eventos.
    # ---
    # Watching starts BEFORE reconciling on purpose: reconciling a
    # large folder takes minutes, and files created locally during
    # that window must still reach quarantine. The other order would
    # lose those events.
    for folder in valid_folders:
        observer = start_watching(client, folder)
        _active_observers[folder] = observer
        logger.info("Vigilancia retomada sobre: %s", folder)

    if missing_folders:
        save_watched_folders(_active_observers.keys())

    icon.notify(
        f"Vigilancia retomada sobre {len(valid_folders)} "
        "carpeta(s) de la sesión anterior. Verificando "
        "integridad...",
        title="Agente H28",
    )

    # Reconciliación automática al arrancar (S034). Cada carpeta se
    # protege por separado: que una falle no puede impedir que las
    # demás se reconcilien, ni tumbar el arranque del agente.
    # ---
    # Automatic reconciliation on startup (S034). Each folder is
    # guarded separately: one failing must neither prevent the
    # others from being reconciled nor bring down agent startup.
    for folder in valid_folders:
        try:
            _run_reconciliation(icon, client, folder)
        except Exception as error:
            logger.error(
                "Fallo en la reconciliación automática de arranque "
                "sobre %s: %s", folder, error,
            )
            append_event(
                "Reconciliacion", folder, f"Error: {error}",
            )


def _quit_agent(icon, _menu_item):
    """Stop every observer and exit the agent.
    ---
    Detiene todos los observadores y sale del agente.
    """
    logger.info("Cerrando el agente: deteniendo %d vigilantes.",
                len(_active_observers))
    for observer in _active_observers.values():
        observer.stop()
    for observer in _active_observers.values():
        observer.join()
    icon.stop()


def main():
    """Start the tray icon and block until the user exits.
    ---
    Arranca el icono de bandeja y bloquea hasta que el usuario
    salga.
    """
    _configure_logging()
    logger.info("Agente H28 arrancado.")

    menu = pystray.Menu(
        pystray.MenuItem(
            "Seleccionar carpeta y copiar", _select_folder_and_copy
        ),
        pystray.MenuItem(
            "Verificar y reparar carpeta", _verify_and_repair_folder
        ),
        pystray.MenuItem("Auditar carpeta (Fase 2)", _audit_folder),
        pystray.MenuItem("Ver historial", _show_history),
        pystray.MenuItem("Salir", _quit_agent),
    )
    icon = pystray.Icon(
        "h28_migration_agent",
        _build_tray_image(),
        "EnterpriseBot — Agente de Migracion H28",
        menu=menu,
    )
    icon.run(setup=_resume_watched_folders)


if __name__ == "__main__":
    main()
