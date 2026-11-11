# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/tools/itv_local_check.py
"""
Local half of the ITV check: compares the ITV report of EnterpriseBot
with the local OneDrive tree (DOC. MAQUINAS) and writes the final
Markdown report. Standard library only.

---

H31 (S150). Mitad local de la comprobación de ITV (tarea programada de
la Hoja de Ruta S150). Recibe el JSON de `itv_documentation_report`
(EnterpriseBot) y el árbol local de OneDrive que contiene
`DOC. MAQUINAS`, y escribe el informe final en Markdown.

Corre en el PC de Miguel Ángel (shell del puente de la app de
escritorio, carpeta `DOC. MAQUINAS` conectada); solo lee, nunca toca
el árbol local.

Por cada documento de ITV de EnterpriseBot busca en local un archivo
con el mismo nombre y el mismo MD5:
- primero en la ruta exacta que dice EnterpriseBot;
- si no, por nombre en todo `DOC. MAQUINAS` (en S150 se vio que muchas
  carpetas de máquina tienen en local otro nombre que en el cubo, p.
  ej. con la empresa al final: "DOCUMENT 1245LJB (MERCEDES V ALE) (GR)").
Cuenta el documento cuya caducidad es la fecha de ITV del vehículo; si
no hay ninguno, todos. Además lista los archivos con "ITV" en el nombre
que hay en local junto a ese documento y que EnterpriseBot no tiene
(p. ej. una ITV nueva escaneada en local y no subida).

Uso:
    python3 itv_local_check.py <informe.json> <raiz> <salida.md>
donde <raiz> es la carpeta que contiene `DOC. MAQUINAS`.
"""
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

LOCAL_ROOT = "DOC. MAQUINAS"
QUARANTINE_PREFIX = "_CUARENTENA/"
HEARTBEAT_EVERY = 10


def _log(log_file, text):
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
    print(line, flush=True)
    log_file.write(line + "\n")
    log_file.flush()


def _nfc(text):
    return unicodedata.normalize("NFC", text)


def _md5(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _index(root):
    """
    Map each file name (NFC) to its paths under DOC. MAQUINAS.

    ---

    Índice nombre de archivo (NFC) -> rutas relativas dentro de
    DOC. MAQUINAS. Solo metadatos: no descarga nada de OneDrive.
    """
    index = {}
    base = os.path.join(root, LOCAL_ROOT)
    for folder, _dirs, files in os.walk(base):
        for name in files:
            rel = os.path.relpath(os.path.join(folder, name), root)
            index.setdefault(_nfc(name), []).append(
                _nfc(rel.replace(os.sep, "/")))
    return index


def _compact(text):
    return re.sub(r"[^A-Z0-9]", "", _nfc(text).upper())


def _locate(root, index, document, plate):
    """
    Return (state, local relative path or "") for one ITV document.

    ---

    Devuelve (estado, ruta local o ""): "ok", "nombre" (mismo
    contenido con otro nombre), "md5" (mismo nombre, otro contenido) o
    "falta". El caso "nombre" sale de los documentos que el cubo tiene
    con el nombre canónico del panel (p. ej. "FURGLAR_ITV_20261119.pdf")
    y en local con el original: se busca su MD5 entre los archivos con
    "ITV" en el nombre cuya ruta lleva la matrícula del vehículo.
    """
    expected = _nfc(document["local_path"])
    if expected.startswith(QUARANTINE_PREFIX):
        expected = expected[len(QUARANTINE_PREFIX):]
    candidates = [expected] if os.path.isfile(
        os.path.join(root, expected)) else []
    name = expected.rsplit("/", 1)[-1]
    candidates += [p for p in index.get(name, []) if p != expected]
    seen_other = ""
    for rel in candidates:
        if not document["md5"] or _md5(os.path.join(root, rel)) == (
                document["md5"]):
            return "ok", rel
        seen_other = seen_other or rel
    if seen_other:
        return "md5", seen_other
    key = _compact(plate)
    if document["md5"] and len(key) >= 5:
        for name, paths in index.items():
            if "ITV" not in name.upper():
                continue
            for rel in paths:
                if key in _compact(rel) and _md5(
                        os.path.join(root, rel)) == document["md5"]:
                    return "nombre", rel
    return "falta", ""


def _latest_itv_files(root, index, plate, limit=2):
    """
    Newest local files with "ITV" in the name whose path carries the
    plate, outside OBSOLETOS.

    ---

    Los archivos locales más recientes con "ITV" en el nombre cuya ruta
    lleva la matrícula, fuera de OBSOLETOS. En S150 los documentos de
    ITV que el panel separó de una "FICHA TECNICA + ITV" (p. ej.
    FURGLAR) no tienen gemelo exacto en local: en local está el PDF
    combinado.
    """
    key = _compact(plate)
    if len(key) < 5:
        return []
    found = []
    for name, paths in index.items():
        if "ITV" not in name.upper():
            continue
        for rel in paths:
            if key in _compact(rel) and "OBSOLET" not in rel.upper():
                found.append((os.path.getmtime(os.path.join(root, rel)),
                              name))
    return [name for _mtime, name in sorted(found, reverse=True)[:limit]]


def _vehicle(root, index, vehicle):
    docs = [d for d in vehicle["documents"] if d["matches_itv"]] or (
        vehicle["documents"])
    problems = []
    folders = set()
    newest = 0.0
    for document in docs:
        state, rel = _locate(root, index, document, vehicle["plate"])
        if rel:
            folders.add(rel.rsplit("/", 1)[0])
            newest = max(newest, os.path.getmtime(os.path.join(root, rel)))
        if state == "nombre":
            problems.append("«%s» está en local con otro nombre (%s)"
                            % (document["name"], rel))
        elif state == "md5":
            problems.append("«%s» está en local con otro contenido (%s)"
                            % (document["name"], rel))
        elif state == "falta":
            hints = _latest_itv_files(root, index, vehicle["plate"])
            problems.append("«%s» no está en local%s" % (
                document["local_path"].rsplit("/", 1)[-1],
                " (lo último de ITV en local: %s)" % ", ".join(
                    "«%s»" % h for h in hints) if hints else ""))
    # Solo los archivos de ITV más nuevos (fecha de modificación) que el
    # documento de EnterpriseBot: una ITV escaneada en local y no subida.
    known = {_nfc(d["local_path"].rsplit("/", 1)[-1])
             for d in vehicle["documents"]}
    extra = []
    for folder in sorted(folders):
        path = os.path.join(root, folder)
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if (os.path.isfile(full) and "ITV" in name.upper()
                    and _nfc(name) not in known
                    and os.path.getmtime(full) > newest):
                extra.append(name)
    return problems, sorted(folders), extra


def main():
    report_path, root, output_path = sys.argv[1:4]
    with open(report_path, encoding="utf-8") as handle:
        report = json.load(handle)
    with open(output_path + ".log", "a", encoding="utf-8") as log_file:
        _log(log_file, "Indexando %s..." % os.path.join(root, LOCAL_ROOT))
        index = _index(root)
        _log(log_file, "Archivos en local: %d." % sum(
            len(v) for v in index.values()))
        vehicles = report["vehicles"]
        rows = []
        for position, vehicle in enumerate(vehicles, start=1):
            problems, folders, extra = _vehicle(root, index, vehicle)
            rows.append((vehicle, problems, folders, extra))
            _log(log_file, "%d/%d %s: %s" % (
                position, len(vehicles), vehicle["code"],
                "; ".join(problems) or "al día en local"))
            if position % HEARTBEAT_EVERY == 0:
                _log(log_file, "Progreso: %d/%d (%d%%)" % (
                    position, len(vehicles), position * 100 // len(
                        vehicles)))
    _write(report, rows, output_path)
    print("Informe: %s" % output_path, flush=True)


def _write(report, rows, output_path):
    both_ok = sum(1 for v, p, _f, _e in rows
                  if not p and v["enterprisebot"] == "al día")
    lines = [
        "# Informe de ITV — %s" % report["today"],
        "",
        "Vehículos activos con la ITV hasta el %s (%d días) o ya vencida: "
        "**%d**. Al día en EnterpriseBot y en local: **%d**."
        % (report["limit"], report["days"], len(rows), both_ok),
        "",
        "| Vehículo | Matrícula | ITV | Días | EnterpriseBot | Local |",
        "|---|---|---|---|---|---|",
    ]
    ordered = sorted(rows, key=lambda r: (
        r[0]["days_left"] < 0, abs(r[0]["days_left"])))
    for vehicle, problems, _folders, extra in ordered:
        local = "; ".join(problems) or "al día"
        if extra:
            local += "; en local hay una ITV más nueva: %s" % ", ".join(
                "«%s»" % name for name in extra)
        lines.append("| %s | %s | %s | %d | %s | %s |" % (
            vehicle["code"], vehicle["plate"],
            datetime.strptime(vehicle["itv_due"], "%Y-%m-%d").strftime(
                "%d/%m/%Y"), vehicle["days_left"],
            vehicle["enterprisebot"], local))
    # S150: lo que va en el correo a Alejandro Alvarez. Vehiculos con la
    # ITV vencida cuya ITV nueva no esta en el panel (por eso sale
    # vencida) ni en local (ningun archivo de ITV mas nuevo).
    missing = [r for r in ordered
               if r[0]["days_left"] < 0 and not r[3]]
    lines += [
        "",
        "## ITV vencida sin la ITV nueva ni en el panel ni en local",
        "",
    ]
    if missing:
        lines += ["| Vehículo | Matrícula | ITV vencida el | Días vencida |",
                  "|---|---|---|---|"]
        for vehicle, _problems, _folders, _extra in missing:
            lines.append("| %s | %s | %s | %d |" % (
                vehicle["code"], vehicle["plate"],
                datetime.strptime(vehicle["itv_due"], "%Y-%m-%d").strftime(
                    "%d/%m/%Y"), -vehicle["days_left"]))
    else:
        lines.append("Ninguno.")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
