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

import ctypes
import logging
import os
import sys
import threading
import time
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
from catchup import sweep_folder
from config import (
    CATCHUP_HEARTBEAT_EVERY_SWEEPS,
    CATCHUP_INTERVAL_SECONDS,
    DIRTY_BUCKET_NAME,
    LOG_FILE_NAME,
)
from gcs_client import MissingCredentialsError, build_client
from history import append_event, load_events
from reconciler import reconcile_folder
from state import load_watched_folders, save_watched_folders
from uploader import upload_folder_recursive

logger = logging.getLogger(__name__)

# Folders being watched in this run, keyed by local path. Persisted
# to disk (state.py) so the agent resumes them automatically on the
# next restart — decision from Miguel Angel, S031.
# ---
# Carpetas vigiladas en esta ejecucion, indexadas por ruta local.
# Se persisten en disco (state.py) para que el agente las retome
# automaticamente en el siguiente reinicio — decision de Miguel
# Angel, S031.
_watched_folders = []

# Estado del hilo del barrido de puesta al dia (S036). El evento de
# despertar permite lanzar un barrido inmediato sin esperar a que
# expire el temporizador; el de parada, cerrar el agente sin esperar
# media hora.
# ---
# Catch-up sweep thread state (S036). The wake event allows an
# immediate sweep without waiting out the timer; the stop event lets
# the agent close without waiting half an hour.
_catchup_thread = None
_catchup_stop_event = threading.Event()
_catchup_wake_event = threading.Event()

# Raiz Tk unica y oculta de todo el agente, creada bajo demanda en el
# hilo del bucle de mensajes -- que es donde pystray ejecuta los
# callbacks de menu.
#
# Origen real (S035): cada funcion creaba su propia `tk.Tk()` y la
# destruia ANTES de los `messagebox` posteriores. Sin raiz viva y sin
# `parent=`, Tkinter se fabrica una raiz implicita para poder dibujar
# el dialogo; esa raiz nace visible, sin un solo widget dentro -- una
# ventana vacia -- y nadie la destruye nunca. Al abrir despues el
# historial coexistian dos raices Tk en el mismo proceso, caso roto de
# fabrica: la ventana no dibujaba sus widgets, su bucle de eventos no
# atendia y solo se podia cerrar desde el administrador de tareas.
# ---
# Single hidden Tk root for the whole agent, created on demand on the
# message-loop thread, where pystray runs menu callbacks.
#
# Real origin (S035): each function created its own `tk.Tk()` and
# destroyed it BEFORE the later `messagebox` calls. With no live root
# and no `parent=`, Tkinter builds an implicit root to draw the
# dialog; that root is born visible, with no widgets at all -- an
# empty window -- and nobody ever destroys it.
_tk_root = None


def _get_tk_root():
    """Return the shared hidden Tk root, creating it once.
    ---
    Devuelve la raiz Tk compartida y oculta, creandola una sola vez.

    Nunca se destruye durante la vida del agente: destruirla obligaria
    a Tkinter a fabricar una raiz implicita en el siguiente dialogo,
    que es exactamente el fallo que esta funcion existe para evitar.
    ---
    It is never destroyed while the agent lives: destroying it would
    force Tkinter to build an implicit root on the next dialog, which
    is precisely the bug this function exists to prevent.
    """
    global _tk_root
    if _tk_root is not None:
        try:
            _tk_root.winfo_exists()
            return _tk_root
        except tk.TclError:
            _tk_root = None
    _tk_root = tk.Tk()
    _tk_root.withdraw()
    _tk_root.attributes("-topmost", True)
    return _tk_root


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

    # Fase de comparacion: la larga. Se registra aparte de la de
    # reparacion porque miden cosas distintas -- aqui el total son
    # todos los archivos de la carpeta, alli solo las diferencias
    # encontradas. Los MB leidos son lo unico que deja estimar cuanto
    # queda: en S035 hubo que mirar el `ReadTransferCount` del proceso
    # en Windows para saberlo, porque el agente no lo decia.
    # ---
    # Comparison phase: the long one. Logged separately from the
    # repair phase because they measure different things. The MB read
    # are the only figure that allows estimating what is left.
    def _log_scan_progress(checked_count, total_count, hashed_bytes):
        logger.info(
            "Comprobando %s: %d/%d archivos, %d MB leidos",
            selected_folder, checked_count, total_count,
            hashed_bytes // (1024 * 1024),
        )

    quarantined_count, already_queued_count, needs_decision_paths, \
        pending_hydration_paths, unrecoverable_paths = reconcile_folder(
            client, DIRTY_BUCKET_NAME, selected_folder,
            _log_reconcile_progress, _log_scan_progress,
        )

    if not any((
        quarantined_count, already_queued_count,
        needs_decision_paths, pending_hydration_paths,
        unrecoverable_paths,
    )):
        summary = "Todo correcto, sin huecos"
    else:
        parts = [f"{quarantined_count} a cuarentena"]
        if already_queued_count:
            parts.append(f"{already_queued_count} ya en cola")
        if needs_decision_paths:
            parts.append(
                f"{len(needs_decision_paths)} pendiente(s) de decisión"
            )
        if pending_hydration_paths:
            parts.append(
                f"{len(pending_hydration_paths)} descargando de "
                "OneDrive"
            )
        if unrecoverable_paths:
            parts.append(
                f"{len(unrecoverable_paths)} irrecuperable(s)"
            )
        summary = ", ".join(parts)

    # La carpeta se nombra en la notificacion desde S034: al
    # ejecutarse la reconciliacion automaticamente sobre varias
    # carpetas al arrancar, dos avisos sin nombre son
    # indistinguibles entre si. Detectado en la primera ejecucion
    # real de la reconciliacion de arranque, corregido en el acto.
    # ---
    # The folder is named in the notification since S034: with
    # reconciliation running automatically over several folders at
    # startup, two unnamed notices are indistinguishable. Spotted on
    # the first real run of the startup reconciliation, fixed on the
    # spot.
    folder_label = os.path.basename(os.path.normpath(selected_folder))

    if unrecoverable_paths or needs_decision_paths:
        icon.notify(
            f"Reconciliación de {folder_label}: {summary}. "
            "Ver el log para el detalle.",
            title="Agente H28",
        )
    else:
        icon.notify(
            f"Reconciliación de {folder_label}: {summary}.",
            title="Agente H28",
        )

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
    root = _get_tk_root()
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta a verificar y reparar (H28)",
        parent=root,
    )

    if not selected_folder:
        return
    selected_folder = os.path.normpath(selected_folder)

    try:
        client = build_client()
    except MissingCredentialsError as error:
        messagebox.showerror("Agente H28", str(error), parent=root)
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
    root = _get_tk_root()
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta a auditar (H28 Fase 2)",
        parent=root,
    )
    if not selected_folder:
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
            parent=root,
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
    icon.notify(f"Auditoría terminada: {summary}.", title="Agente H28")
    append_event("Auditoria", selected_folder, summary)

    messagebox.showinfo(
        "Agente H28",
        f"Auditoría completada.\n\n{summary_text}\n\n"
        f"Resumen guardado en:\n{summary_path}",
        parent=root,
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

    window = tk.Toplevel(_get_tk_root())
    window.title("Agente H28 — Historial")
    window.geometry("820x420")
    window.attributes("-topmost", True)
    window.protocol("WM_DELETE_WINDOW", window.destroy)

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

    # `wait_window` bombea eventos hasta que la ventana se destruye,
    # sin arrancar un segundo bucle principal. El `mainloop()` que
    # habia aqui montaba un bucle propio sobre una raiz propia, que es
    # la otra mitad del fallo de S035.
    # ---
    # `wait_window` pumps events until the window is destroyed,
    # without starting a second main loop. The `mainloop()` that used
    # to be here ran its own loop on its own root -- the other half of
    # the S035 bug.
    window.wait_window()


def _show_watched_folders(icon, _menu_item):
    """Open a window listing the folders currently being watched,
    with the option to remove one from the watch list.
    ---
    Abre una ventana con las carpetas actualmente vigiladas, con la
    opcion de quitar una de la lista de vigiladas.

    S54, peticion explicita de Miguel Angel: antes solo se podia
    consultar pidiendo un comando de PowerShell -- "un engorro". Y,
    tras verlo en uso, pidio ademas poder quitar una carpeta sin
    salir del agente ("deberiamos tener un CRUD ... no solamente un
    visor").

    Quitar una carpeta de aqui SOLO detiene el barrido periodico de
    puesta al dia sobre ella (deja de aparecer en el siguiente ciclo
    de _run_catchup_pass) -- nunca borra nada de lo ya subido ni toca
    el cubo. Se puede retomar mas adelante con "Vigilar carpeta ya
    migrada".
    """
    root = _get_tk_root()

    window = tk.Toplevel(root)
    window.title("Agente H28 — Carpetas vigiladas")
    window.geometry("820x340")
    window.attributes("-topmost", True)
    window.protocol("WM_DELETE_WINDOW", window.destroy)

    columns = ("index", "folder")
    tree = ttk.Treeview(window, columns=columns, show="headings")
    tree.heading("index", text="#")
    tree.heading("folder", text="Carpeta vigilada")
    tree.column("index", width=40, anchor="center")
    tree.column("folder", width=760, anchor="w")

    scrollbar = ttk.Scrollbar(
        window, orient="vertical", command=tree.yview,
    )
    tree.configure(yscrollcommand=scrollbar.set)

    button_bar = tk.Frame(window)
    button_bar.pack(side="bottom", fill="x", pady=6)

    def _refresh_tree():
        tree.delete(*tree.get_children())
        if not _watched_folders:
            tree.insert("", "end", values=(
                "", "Ninguna carpeta vigilada todavia",
            ))
            return
        for position, folder in enumerate(_watched_folders, start=1):
            tree.insert("", "end", values=(position, folder))

    def _remove_selected():
        selection = tree.selection()
        if not selection:
            messagebox.showinfo(
                "Agente H28",
                "Selecciona primero una carpeta de la lista.",
                parent=window,
            )
            return
        values = tree.item(selection[0], "values")
        folder = values[1] if len(values) > 1 else None
        if not folder or folder not in _watched_folders:
            return

        confirmed = messagebox.askyesno(
            "Agente H28",
            f"Se va a dejar de vigilar:\n{folder}\n\n"
            "Esto NO borra nada de lo ya subido al cubo -- solo "
            "detiene el barrido periodico de puesta al dia sobre "
            "esta carpeta. Se puede retomar mas adelante.\n\n"
            "¿Continuar?",
            parent=window,
        )
        if not confirmed:
            return

        _watched_folders.remove(folder)
        save_watched_folders(_watched_folders)
        append_event(
            "Vigilancia detenida", folder, "Quitada por Miguel Angel",
        )
        logger.info("Carpeta quitada de vigiladas: %s", folder)
        _refresh_tree()

    tk.Button(
        button_bar, text="Quitar de vigiladas", command=_remove_selected,
    ).pack(side="left", padx=8)
    tk.Button(
        button_bar, text="Cerrar", command=window.destroy,
    ).pack(side="right", padx=8)

    _refresh_tree()
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    window.wait_window()


def _watch_migrated_folder(icon, _menu_item):
    """Resume continuous watching over a folder that is already
    fully migrated, closing any real gap first via reconciliation --
    never doing the blind full "Copia inicial" (upload_folder_recursive)
    a second time.
    ---
    Retoma la vigilancia continua sobre una carpeta que ya esta
    migrada por completo, cerrando primero cualquier hueco real via
    reconciliacion -- sin volver a hacer nunca la "Copia inicial"
    ciega (upload_folder_recursive) por segunda vez.

    S54, hueco real descubierto y cerrado a peticion explicita de
    Miguel Angel: hasta ahora solo existian dos caminos para empezar
    a vigilar una carpeta -- "Seleccionar carpeta y copiar" (sube
    TODO sin comprobar, pensada para una carpeta nueva jamas migrada)
    o "Verificar y reparar carpeta" (repara el hueco real por hash,
    pero no deja vigilancia continua activa). Ninguno de los dos sirve
    para el caso real de esta sesion: una carpeta ya migrada por
    completo (DOC. MAQUINAS / DOC. PERSONAL) que necesita cerrar solo
    los dias reales de hueco y retomar la vigilancia, sin repetir la
    copia entera.
    """
    root = _get_tk_root()
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta YA MIGRADA a vigilar (H28)",
        parent=root,
    )

    if not selected_folder:
        return
    selected_folder = os.path.normpath(selected_folder)

    if selected_folder in _watched_folders:
        messagebox.showinfo(
            "Agente H28",
            f"Esta carpeta ya se esta vigilando:\n{selected_folder}",
            parent=root,
        )
        return

    confirmed = messagebox.askyesno(
        "Agente H28",
        f"Se va a reconciliar y retomar la vigilancia continua de:\n"
        f"{selected_folder}\n\n"
        "Esto NO vuelve a subir los archivos ya migrados -- solo "
        "compara por hash contra lo que ya hay en el cubo y manda a "
        "cuarentena lo que falte de verdad. Puede tardar varios "
        "minutos en carpetas grandes.\n\n¿Continuar?",
        parent=root,
    )
    if not confirmed:
        return

    try:
        client = build_client()
    except MissingCredentialsError as error:
        messagebox.showerror("Agente H28", str(error), parent=root)
        return

    icon.notify(
        f"Reconciliando {selected_folder}...", title="Agente H28",
    )
    _run_reconciliation(icon, client, selected_folder)

    _watched_folders.append(selected_folder)
    save_watched_folders(_watched_folders)
    _start_catchup_thread(icon)
    icon.notify(
        f"Vigilancia continua retomada sobre:\n{selected_folder}",
        title="Agente H28",
    )
    append_event(
        "Vigilancia retomada", selected_folder,
        "Reconciliada y anadida a carpetas vigiladas",
    )


def _select_folder_and_copy(icon, _menu_item):
    """Open the folder picker, then copy and watch it.
    ---
    Abre el selector de carpetas, y la copia y vigila.
    """
    root = _get_tk_root()
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta a migrar (H28)",
        parent=root,
    )

    if not selected_folder:
        return
    selected_folder = os.path.normpath(selected_folder)

    if selected_folder in _watched_folders:
        messagebox.showinfo(
            "Agente H28",
            f"Esta carpeta ya se esta vigilando:\n{selected_folder}",
            parent=root,
        )
        return

    try:
        client = build_client()
    except MissingCredentialsError as error:
        messagebox.showerror("Agente H28", str(error), parent=root)
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

    _watched_folders.append(selected_folder)
    save_watched_folders(_watched_folders)
    # Por si esta es la primera carpeta de una ejecución que arrancó
    # sin ninguna persistida: el hilo es idempotente y no se duplica.
    # ---
    # In case this is the first folder of a run that started with
    # none persisted: starting the thread is idempotent.
    _start_catchup_thread(icon)
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
        _watched_folders.append(folder)
        logger.info("Vigilancia retomada sobre: %s", folder)

    if missing_folders:
        save_watched_folders(_watched_folders)

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

    # El barrido arranca DESPUÉS de la reconciliación, a propósito.
    # La reconciliación compara contra el cubo de verdad y establece
    # el estado real; el barrido solo mantiene el delta a partir de
    # ahí. Al revés, el primer barrido sembraría su índice sobre un
    # árbol todavía sin verificar.
    # ---
    # The sweep starts AFTER reconciliation on purpose: reconciliation
    # compares against the bucket itself and establishes the real
    # state; the sweep only maintains the delta from there.
    _start_catchup_thread(icon)


def _run_catchup_pass(icon, client):
    """Sweep every watched folder once and report only if there is
    news.
    ---
    Barre una vez cada carpeta vigilada e informa solo si hay
    novedades.

    Cada carpeta va dentro de su propio guardado de errores, mismo
    criterio que la reconciliacion de arranque: que una falle no
    puede impedir que las demas se barran ni tumbar el hilo.

    Returns
    -------
    bool
        True si alguna carpeta ha dado novedades. Lo usa el bucle
        para decidir si emitir latido o callarse.
        ---
        True when any folder produced news; used by the loop to
        decide whether to beat or stay quiet.
    ---
    Each folder is guarded separately, same criterion as the startup
    reconciliation: one failing must not stop the others.
    """
    had_news = False
    for selected_folder in list(_watched_folders):
        try:
            resumen = sweep_folder(client, selected_folder)
        except Exception as error:  # noqa: BLE001
            logger.exception(
                "Puesta al dia: fallo barriendo %s: %s",
                selected_folder, error,
            )
            append_event(
                "Puesta al dia", selected_folder, f"Error: {error}",
            )
            had_news = True
            continue

        # Solo se notifica cuando hay algo que contar. Un aviso cada
        # minuto diciendo "sin novedades" seria ruido puro y acabaria
        # haciendo que no se mire ninguno.
        # ---
        # Only notified when there is something to report.
        if resumen["seeded"]:
            append_event(
                "Puesta al dia", selected_folder,
                f"Indice sembrado con {resumen['total']} archivos",
            )
            had_news = True
            continue

        if not (resumen["uploaded"] or resumen["failed"]
                or resumen["hydration_requested"]):
            continue

        had_news = True

        partes = []
        if resumen["uploaded"]:
            partes.append(f"{resumen['uploaded']} a cuarentena")
        if resumen["hydration_requested"]:
            partes.append(
                f"{resumen['hydration_requested']} descargando de "
                "OneDrive"
            )
        if resumen["failed"]:
            partes.append(f"{resumen['failed']} fallido(s)")
        texto = ", ".join(partes)

        folder_label = os.path.basename(
            os.path.normpath(selected_folder)
        )
        icon.notify(
            f"Puesta al día de {folder_label}: {texto}.",
            title="Agente H28",
        )
        append_event("Puesta al dia", selected_folder, texto)

    return had_news


def _catchup_loop(icon):
    """Run the catch-up sweep every CATCHUP_INTERVAL_SECONDS.
    ---
    Ejecuta el barrido de puesta al dia cada
    CATCHUP_INTERVAL_SECONDS.

    Vive en su propio hilo a proposito. Los callbacks de menu de
    `pystray` se ejecutan en el bucle de mensajes, y por eso la
    auditoria bloquea el menu mientras corre -- limitacion conocida
    anotada en el anexo (S034). El barrido no puede repetir ese
    error: corre cada minuto, indefinidamente.

    Mide su propia duracion y avisa si un ciclo tarda mas que el
    intervalo. A cadencia de un minuto sobre ~37.500 archivos eso
    deja de ser teorico: si el barrido tarda mas de lo que dura el
    intervalo, el hilo encadena barridos sin descanso y castiga el
    disco de la maquina en la que se esta trabajando. Nadie ha medido
    todavia cuanto tarda de verdad sobre el arbol de produccion, asi
    que se mide en vez de suponerlo.
    ---
    Lives in its own thread on purpose, and measures its own
    duration, warning when a cycle takes longer than the interval. At
    a one-minute cadence over ~37,500 files that is no longer
    theoretical: a sweep slower than its interval would chain sweeps
    back to back. Nobody has measured the real duration against the
    production tree yet, so it is measured rather than assumed.
    """
    uneventful_sweeps = 0
    while not _catchup_stop_event.is_set():
        # `wait` devuelve antes de tiempo si alguien pide un barrido
        # inmediato, y permite cerrar el agente sin esperar a que
        # expire el temporizador.
        # ---
        # `wait` returns early when an immediate sweep is requested,
        # and lets the agent shut down without waiting out the timer.
        _catchup_wake_event.wait(CATCHUP_INTERVAL_SECONDS)
        _catchup_wake_event.clear()
        if _catchup_stop_event.is_set():
            break
        if not _watched_folders:
            continue
        try:
            client = build_client()
        except MissingCredentialsError as error:
            logger.error(
                "Puesta al dia: no se pudo construir el cliente: %s",
                error,
            )
            continue

        started_at = time.monotonic()
        had_news = _run_catchup_pass(icon, client)
        elapsed_seconds = time.monotonic() - started_at

        if elapsed_seconds > CATCHUP_INTERVAL_SECONDS:
            logger.warning(
                "Puesta al dia: el barrido ha tardado %.1f s, mas que "
                "el intervalo de %d s. El siguiente arranca de "
                "inmediato, sin pausa. Conviene subir "
                "CATCHUP_INTERVAL_SECONDS.",
                elapsed_seconds, CATCHUP_INTERVAL_SECONDS,
            )

        if had_news:
            uneventful_sweeps = 0
            continue

        uneventful_sweeps += 1
        if uneventful_sweeps % CATCHUP_HEARTBEAT_EVERY_SWEEPS == 0:
            logger.info(
                "Puesta al dia: %d barridos seguidos sin novedades. "
                "Ultimo ciclo: %.1f s.",
                uneventful_sweeps, elapsed_seconds,
            )


def _start_catchup_thread(icon):
    """Start the catch-up sweep thread once.
    ---
    Arranca una sola vez el hilo del barrido de puesta al dia.
    """
    global _catchup_thread
    if _catchup_thread is not None and _catchup_thread.is_alive():
        return
    _catchup_thread = threading.Thread(
        target=_catchup_loop, args=(icon,), daemon=True,
    )
    _catchup_thread.start()
    logger.info(
        "Puesta al dia: barrido periodico activo cada %d segundos.",
        CATCHUP_INTERVAL_SECONDS,
    )


def _catchup_now(icon, _menu_item):
    """Wake the catch-up thread so it sweeps immediately.
    ---
    Despierta al hilo de puesta al dia para que barra ya.

    No hace el barrido en este hilo: solo levanta el evento y vuelve
    de inmediato. Asi el menu de bandeja nunca se queda bloqueado,
    que es la limitacion que si tiene la auditoria.
    ---
    Does not sweep on this thread: it just raises the event and
    returns at once, so the tray menu is never blocked.
    """
    if not _watched_folders:
        icon.notify(
            "No hay ninguna carpeta vigilada que poner al día.",
            title="Agente H28",
        )
        return
    _catchup_wake_event.set()
    icon.notify(
        "Puesta al día lanzada en segundo plano.",
        title="Agente H28",
    )


def _quit_agent(icon, _menu_item):
    """Stop the catch-up sweep and exit the agent.
    ---
    Detiene el barrido de puesta al dia y sale del agente.
    """
    logger.info(
        "Cerrando el agente: deteniendo el barrido sobre %d carpeta(s).",
        len(_watched_folders),
    )
    # Se levantan los dos eventos: el de parada para que el bucle
    # salga, y el de despertar para que no se quede esperando a que
    # expire el temporizador de media hora.
    # ---
    # Both events are raised: stop so the loop exits, and wake so it
    # does not sit waiting out the half-hour timer.
    _catchup_stop_event.set()
    _catchup_wake_event.set()
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
        pystray.MenuItem(
            "Vigilar carpeta ya migrada", _watch_migrated_folder
        ),
        pystray.MenuItem("Poner al día ahora", _catchup_now),
        pystray.MenuItem("Auditar carpeta (Fase 2)", _audit_folder),
        pystray.MenuItem("Carpetas vigiladas", _show_watched_folders),
        pystray.MenuItem("Ver historial", _show_history),
        pystray.MenuItem("Salir", _quit_agent),
    )
    icon = pystray.Icon(
        "h28_migration_agent",
        _build_tray_image(),
        "EnterpriseBot — Agente de Migración H28",
        menu=menu,
    )
    icon.run(setup=_resume_watched_folders)


# Incidente real S66: 3 procesos AgenteMigracionH28.exe corriendo a la
# vez en el PC de Miguel Angel (tasklist real: dos con horas de CPU
# reales distintas -- lanzamientos independientes en momentos
# distintos -- mas uno recien arrancado), sin que la Tarea Programada
# ("Durante el inicio de sesion") lo detectara como duplicado desde su
# propio lado. Causa raiz confirmada leyendo este archivo completo:
# nunca existio ningun mecanismo de instancia unica -- nada impedia
# que sucesivos inicios de sesion (o un doble lanzamiento manual)
# dejaran instancias huerfanas corriendo en paralelo, escribiendo
# watched_folders.json/history.json a la vez (riesgo real de
# sobrescritura cruzada) y subiendo la misma documentacion nueva por
# duplicado a cuarentena.
#
# Mutex nombrado de Windows via ctypes (sin dependencia nueva): el
# primer proceso que llama CreateMutexW se queda con el mutex: los
# siguientes reciben ERROR_ALREADY_EXISTS (183) y salen de inmediato
# con aviso visible, en vez de arrancar una segunda copia silenciosa.
# El handle se libera solo al terminar el proceso (Windows lo hace
# automaticamente) -- no hace falta cerrarlo a mano.
# ---
# Real incident S66: 3 AgenteMigracionH28.exe processes running at
# once on Miguel Angel's PC (real tasklist: two with distinct real CPU
# times -- independent launches at different times -- plus one just
# started), without the Scheduled Task ("At log on") detecting it as
# a duplicate from its own side. Root cause confirmed by reading this
# whole file: no single-instance mechanism ever existed -- nothing
# stopped successive log-ons (or a manual double-launch) from leaving
# orphaned instances running in parallel, writing watched_folders.json/
# history.json at the same time (real risk of cross-overwrite) and
# uploading the same new documentation twice to quarantine.
#
# Windows named mutex via ctypes (no new dependency): the first
# process to call CreateMutexW keeps the mutex; subsequent ones get
# ERROR_ALREADY_EXISTS (183) and exit immediately with a visible
# warning, instead of starting a second silent copy. The handle is
# released automatically by Windows when the process ends -- no
# manual close needed.
_SINGLE_INSTANCE_MUTEX_NAME = (
    "Global\\EnterpriseBot_H28MigrationAgent_SingleInstance"
)
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance_lock():
    """Return a mutex handle if this is the only running instance,
    None if another instance already holds it.
    ---
    Devuelve un handle de mutex si esta es la unica instancia en
    marcha, None si ya hay otra instancia con el mutex tomado.
    """
    mutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, _SINGLE_INSTANCE_MUTEX_NAME,
    )
    if ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        return None
    return mutex


if __name__ == "__main__":
    _instance_lock = _acquire_single_instance_lock()
    if _instance_lock is None:
        logger.warning(
            "Ya hay una instancia del Agente H28 en ejecucion -- "
            "esta copia se cierra sin arrancar (S66)."
        )
        messagebox.showwarning(
            "Agente H28 ya en ejecución",
            "Ya hay una instancia del Agente de Migración H28 en "
            "ejecución en este PC.\n\n"
            "Revisa el icono en la bandeja del sistema (junto al "
            "reloj) -- puede estar oculto en el desplegable de "
            "iconos ocultos.",
        )
        sys.exit(0)
    main()
