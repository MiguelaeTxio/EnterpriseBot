# C:\EnterpriseBot\AgenteFirmas\agente_firmas.py
"""
S153. EnterpriseBot signing agent (Windows): signs with AutoFirma the
documents generated in the panel's "Firmas" tab, using the company
certificates installed in this PC's Windows store (the private key never
leaves the PC).

---

S153. Agente de firmas de EnterpriseBot (Windows). Recoge del panel los
documentos generados en la pestaña Firmas que esperan firma digital, los
firma con AutoFirma (línea de comandos, almacén de certificados de
Windows: la clave privada no sale de este ordenador) y devuelve los PDF
firmados. Cuenta al panel qué certificados ve, para elegir en la pestaña
con cuál firma cada empresa.

Primera vez: pide el código de vinculación (se genera en la pestaña
Firmas, "Generar código de vinculación") y se pone a arrancar solo al
iniciar sesión (acceso en la carpeta Inicio del usuario). Sin ventana;
su registro queda en %LOCALAPPDATA%\\EnterpriseBot\\AgenteFirmas\\
agente.log. Una sola copia a la vez.
"""
import datetime
import glob
import json
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import tempfile
import time

import requests

SERVER = "https://enterprisebot-miguelaetxio.pythonanywhere.com"
API = "/panel/firmas/agente/"
POLL_SECONDS = 10
HEARTBEAT_SECONDS = 300
SIGN_TIMEOUT_SECONDS = 180
HTTP_TIMEOUT = 60
LOCK_PORT = 47653
APP_NAME = "AgenteFirmas"
VERSION = "3"
CREATE_NO_WINDOW = 0x08000000

DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "EnterpriseBot", APP_NAME)
CODE_FILE = os.path.join(DATA_DIR, "codigo.txt")
LOG_FILE = os.path.join(DATA_DIR, "agente.log")

log = logging.getLogger(APP_NAME)


def setup_logging():
    """
    Rotating log file (and console when there is one).
    ---
    Registro en archivo (rotativo) y en consola si la hay.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(fmt)
    log.addHandler(handler)
    if sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        log.addHandler(console)


def single_instance():
    """
    Hold a local port as a lock; None if another copy is running.
    ---
    Reserva un puerto local como candado; None si ya hay otra copia.
    """
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        return None
    return lock


def ask_code():
    """
    Ask for the link code in a small window.
    ---
    Pide el código de vinculación en una ventanita.
    """
    import tkinter
    from tkinter import messagebox, simpledialog

    root = tkinter.Tk()
    root.withdraw()
    code = simpledialog.askstring(
        "Agente de firmas de EnterpriseBot",
        "Pega el código de vinculación (pestaña Firmas del panel, "
        "\"Generar código de vinculación\"):", parent=root)
    code = (code or "").strip()
    if code:
        messagebox.showinfo(
            "Agente de firmas de EnterpriseBot",
            "Vinculado. El agente se queda funcionando sin ventana y "
            "arrancará solo al iniciar sesión.", parent=root)
    root.destroy()
    return code


def load_code():
    """
    The saved link code, asking for it the first time.
    ---
    El código guardado; la primera vez lo pide y lo guarda.
    """
    if os.path.exists(CODE_FILE):
        with open(CODE_FILE, encoding="utf-8") as handle:
            code = handle.read().strip()
        if code:
            return code
    code = ask_code()
    if code:
        with open(CODE_FILE, "w", encoding="utf-8") as handle:
            handle.write(code)
    return code


def install_autostart():
    """
    Start with the session: a hidden launcher in the Startup folder.
    ---
    Arranque al iniciar sesión: un lanzador sin ventana en la carpeta
    Inicio del usuario (no hace falta ser administrador). Solo si va
    empaquetado (.exe).
    """
    if not getattr(sys, "frozen", False):
        return
    startup = os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft", "Windows",
        "Start Menu", "Programs", "Startup")
    if not os.path.isdir(startup):
        return
    target = os.path.join(startup, "EnterpriseBot Agente de firmas.vbs")
    exe = sys.executable.replace('"', '""')
    content = ('CreateObject("WScript.Shell").Run """%s""", 0, False\r\n'
               % exe)
    try:
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        log.warning("No se ha podido poner el arranque automático: %s", exc)


def find_autofirma():
    """
    Path of AutoFirmaCommandLine.exe, or "".
    ---
    Ruta de AutoFirmaCommandLine.exe (instalación normal de AutoFirma),
    o "" si no está.
    """
    roots = [os.environ.get(name, "") for name in
             ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
              "LOCALAPPDATA")]
    for root in filter(None, roots):
        for pattern in ("AutoFirma\\AutoFirma\\AutoFirmaCommandLine.exe",
                        "AutoFirma\\AutoFirmaCommandLine.exe",
                        "AutoFirma*\\**\\AutoFirmaCommandLine.exe",
                        "Programs\\AutoFirma\\**\\AutoFirmaCommandLine.exe"):
            hits = glob.glob(os.path.join(root, pattern), recursive=True)
            if hits:
                return hits[0]
    return ""


def run(args, timeout):
    """
    Run a command without a window; (returncode, output).
    ---
    Ejecuta un comando sin ventana; devuelve (código, salida).
    """
    completed = subprocess.run(
        args, capture_output=True, timeout=timeout,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
    output = (completed.stdout or b"") + b"\n" + (completed.stderr or b"")
    return completed.returncode, output.decode("utf-8", "replace").strip()


def list_aliases(cli):
    """
    Certificate aliases AutoFirma sees in the Windows store.
    ---
    Los alias de los certificados que AutoFirma ve en el almacén de
    Windows (una línea por alias).
    """
    code, output = run([cli, "listaliases", "-store", "windows"], 120)
    log.info("listaliases (código %s):\n%s", code, output)
    if code != 0:
        raise RuntimeError("AutoFirma no lista los certificados: %s"
                           % output[-500:])
    aliases = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("alias", "---", "usage",
                                                "uso")):
            continue
        aliases.append(line)
    return aliases


# S153 (v3): los certificados con clave privada del almacén de Windows
# (usuario y equipo) con su huella, sujeto y fechas, en JSON. El panel
# saca de ahí la empresa (CIF del "(R: ...)") y descarta los caducados.
CERTIFICATES_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
    "$l=foreach($c in (Get-ChildItem Cert:\\CurrentUser\\My,"
    "Cert:\\LocalMachine\\My|Where-Object {$_.HasPrivateKey})){"
    "[pscustomobject]@{t=$c.Thumbprint;s=$c.Subject;"
    "n=$c.GetNameInfo('SimpleName',$false);f=$c.FriendlyName;"
    "a=$c.NotBefore.ToString('yyyy-MM-dd');"
    "b=$c.NotAfter.ToString('yyyy-MM-dd')}};"
    "ConvertTo-Json -InputObject @($l) -Compress"
)


def list_certificates():
    """
    Certificates with a private key in the Windows store (v3).
    ---
    Los certificados con clave privada del almacén de Windows, con su
    huella, sujeto, nombre y fechas (PowerShell, sin ventana).
    """
    code, output = run(["powershell", "-NoProfile", "-NonInteractive",
                        "-ExecutionPolicy", "Bypass", "-Command",
                        CERTIFICATES_SCRIPT], 120)
    start = output.find("[")
    if code != 0 or start < 0:
        raise RuntimeError("No se pueden leer los certificados de "
                           "Windows: %s" % output[-500:])
    certificates = json.loads(output[start:output.rfind("]") + 1])
    log.info("Certificados de Windows: %s", [
        (c.get("n"), c.get("b")) for c in certificates])
    return certificates


class Agent:
    """
    The polling loop: heartbeat, pending documents, sign, answer.
    ---
    El bucle: latido, documentos pendientes, firmar y devolver.
    """

    def __init__(self, code):
        self.session = requests.Session()
        self.session.headers["Authorization"] = "Bearer " + code
        self.host = "%s (agente v%s)" % (socket.gethostname(), VERSION)
        self.cli = ""
        self.last_heartbeat = 0.0
        self.last_error = ""

    def post(self, path, data=None, files=None):
        response = self.session.post(SERVER + path, data=data or {},
                                     files=files, timeout=HTTP_TIMEOUT)
        if response.status_code == 403:
            raise PermissionError("el panel no acepta el código de "
                                  "vinculación (¿agente dado de baja?)")
        response.raise_for_status()
        return response.json()

    def heartbeat(self):
        self.cli = find_autofirma()
        aliases = None
        certificates = None
        try:
            certificates = list_certificates()
        except Exception as exc:  # noqa: BLE001 -- se informa
            log.warning("%s", exc)
        if not self.cli:
            self.last_error = ("AutoFirma no está instalado en este "
                               "ordenador (firmaelectronica.gob.es)")
        else:
            try:
                aliases = list_aliases(self.cli)
                self.last_error = ""
            except Exception as exc:  # noqa: BLE001 -- se informa
                self.last_error = str(exc)[:1000]
        self.post(API + "latido/", {
            "host": self.host,
            "aliases": json.dumps(aliases) if aliases is not None else "",
            "certificates": (json.dumps(certificates)
                             if certificates is not None else ""),
            "autofirma": self.cli,
            "error": self.last_error,
        })
        self.last_heartbeat = time.time()
        log.info("Latido: AutoFirma=%s, certificados=%s, error=%s",
                 self.cli or "-", aliases, self.last_error or "-")

    def sign_one(self, item):
        log.info("Firmando %s (%s) con '%s' %s", item["id"], item["name"],
                 item["alias"], item.get("thumbprint") or "")
        response = self.session.get(SERVER + item["download"],
                                    timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "entrada.pdf")
            target = os.path.join(tmp, "firmado.pdf")
            with open(source, "wb") as handle:
                handle.write(response.content)
            error = ""
            if not self.cli:
                error = "AutoFirma no está instalado en el ordenador"
            else:
                args = [self.cli, "sign", "-i", source, "-o", target,
                        "-format", "pades", "-store", "windows"]
                # S153 (v3): con huella, el certificado exacto (vigente)
                # que eligió el panel; los nombres se repiten entre
                # certificados caducados y vigentes.
                if item.get("thumbprint"):
                    args += ["-filter",
                             "thumbprint:SHA1:%s" % item["thumbprint"]]
                else:
                    args += ["-alias", item["alias"]]
                # S153: firma visible (recuadro "Firmado digitalmente
                # por..." junto a la imagen de la firma).
                if item.get("config"):
                    args += ["-config", item["config"]]
                try:
                    code, output = run(args, SIGN_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    code, output = -1, ("AutoFirma no ha terminado en %d s "
                                        "(¿pide contraseña o confirmación?)"
                                        % SIGN_TIMEOUT_SECONDS)
                log.info("AutoFirma sign (código %s): %s", code,
                         output[-1000:])
                if code != 0 or not os.path.exists(target):
                    error = "AutoFirma: %s" % (output[-800:] or code)
            if error:
                self.post(item["result"], {"error": error})
                log.warning("Error en %s: %s", item["id"], error)
                return
            with open(target, "rb") as handle:
                self.post(item["result"], files={
                    "signed": (item["name"], handle, "application/pdf")})
        log.info("Firmado y devuelto %s", item["id"])

    def loop(self):
        while True:
            try:
                if time.time() - self.last_heartbeat > HEARTBEAT_SECONDS:
                    self.heartbeat()
                pending = self.post(API + "pendientes/", {
                    "host": self.host, "autofirma": self.cli,
                    "error": self.last_error,
                }).get("files", [])
                for item in pending:
                    try:
                        self.sign_one(item)
                    except PermissionError:
                        raise
                    except Exception as exc:  # noqa: BLE001 -- se informa
                        log.exception("Fallo firmando %s", item.get("id"))
                        try:
                            self.post(item["result"], {
                                "error": "agente: %s" % str(exc)[:800]})
                        except Exception:  # noqa: BLE001
                            pass
                if pending:
                    continue
            except PermissionError as exc:
                log.error("%s. Reintento en 5 minutos.", exc)
                time.sleep(300)
                continue
            except Exception as exc:  # noqa: BLE001 -- sin red, panel caído
                log.warning("Sin conexión con el panel: %s", exc)
                time.sleep(POLL_SECONDS * 3)
                continue
            time.sleep(POLL_SECONDS)


def main():
    """
    Entry point.
    ---
    Arranque: registro, una sola copia, código, arranque automático y
    bucle.
    """
    setup_logging()
    lock = single_instance()
    if lock is None:
        log.info("Ya hay otra copia del agente funcionando; salgo.")
        return
    log.info("Agente de firmas arrancado %s (%s).",
             datetime.datetime.now().isoformat(timespec="seconds"),
             sys.executable)
    code = load_code()
    if not code:
        log.error("Sin código de vinculación; salgo.")
        return
    install_autostart()
    Agent(code).loop()


if __name__ == "__main__":
    main()
