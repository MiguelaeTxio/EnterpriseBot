# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/mail_reader_agent/outlook_reader.py
"""Read mails from an Outlook folder and upload new ones to the bucket.
---
Lee los correos de una carpeta de Outlook y sube al cubo los nuevos.

Miguel Angel (S156): leer los correos que recibe Yolanda "sin quitar
los avisos del propio Outlook". Por eso:

- Se lee cada correo por el modelo de objetos de Outlook (COM) sin
  abrirlo en pantalla: nunca se toca `UnRead`, nunca se llama a
  `Display()`, nunca se mueve, borra ni marca nada. El contador de no
  leidos, la alerta de correo nuevo y las reglas siguen igual.
- Solo se miran los correos recibidos en los ultimos LOOKBACK_DAYS.
- Cada correo va al cubo como una carpeta
  `CORREOS DOCUMENTACION/NUEVOS/<AAAAMMDD-HHMMSS>_<huella>/` con sus
  adjuntos y, la ultima, la ficha `correo.json` (remitente, destino,
  asunto, fecha, cuerpo en texto y lista de adjuntos). Sin ficha, el
  correo esta a medias y se vuelve a subir en la siguiente revision.
- La huella sale del Message-ID de internet (o del EntryID si no
  tiene): el mismo correo nunca se sube dos veces, aunque se mueva de
  carpeta.
"""
import datetime
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile

from config import (
    BUCKET_NAME, LOOKBACK_DAYS, MAIL_JSON_NAME, MAX_BODY_CHARS,
    OL_MAIL_ITEM, PR_ATTACHMENT_HIDDEN, PR_INTERNET_MESSAGE_ID,
    PR_SMTP_ADDRESS, STATE_FILE_NAME, STATE_RETENTION_DAYS, UPLOAD_PREFIX,
    get_data_dir,
)

logger = logging.getLogger(__name__)

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _state_path():
    return os.path.join(get_data_dir(), STATE_FILE_NAME)


def load_state():
    """Previously uploaded mails: {key: {"prefix", "received"}}.
    ---
    Correos ya subidos: {huella: {"prefix", "received"}}.
    """
    try:
        with open(_state_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    """Write the state atomically, forgetting very old entries.
    ---
    Guarda el estado de forma atomica (temporal + reemplazo) y olvida
    lo recibido hace mas de STATE_RETENTION_DAYS.
    """
    limit = (datetime.datetime.now() - datetime.timedelta(
        days=STATE_RETENTION_DAYS)).isoformat()
    state = {key: value for key, value in state.items()
             if value.get("received", "") >= limit}
    temp_path = _state_path() + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)
    os.replace(temp_path, _state_path())


def get_namespace():
    """MAPI namespace of the running (or started) desktop Outlook.
    ---
    Espacio MAPI del Outlook de escritorio. Cada hilo que lo use debe
    haber llamado antes a pythoncom.CoInitialize().
    """
    import win32com.client

    return win32com.client.Dispatch("Outlook.Application").GetNamespace(
        "MAPI")


def pick_folder():
    """Outlook's own folder picker: {"entry_id", "store_id", "path"}.
    ---
    El selector de carpetas del propio Outlook. Devuelve lo necesario
    para volver a abrir la carpeta (o None si se cancela).
    """
    folder = get_namespace().PickFolder()
    if folder is None:
        return None
    return {"entry_id": folder.EntryID, "store_id": folder.StoreID,
            "path": folder.FolderPath}


def _open_folder(namespace, settings):
    return namespace.GetFolderFromID(settings["entry_id"],
                                     settings["store_id"])


def _safe_name(name, fallback):
    name = _UNSAFE_NAME.sub("_", (name or "").strip()).strip(". ")
    return name[:150] or fallback


def _sender_address(item):
    """SMTP address of the sender, also for internal Exchange senders.
    ---
    Direccion SMTP del remitente; para remitentes internos de Exchange
    (tipo "EX") la de su usuario, no el nombre X.500.
    """
    try:
        if item.SenderEmailType == "EX":
            user = item.Sender.GetExchangeUser()
            if user is not None:
                return user.PrimarySmtpAddress or ""
        return item.SenderEmailAddress or ""
    except Exception:  # noqa: BLE001
        return ""


def _recipients(item):
    """[(type, name, address)] of To/CC/BCC.
    ---
    Destinatarios con su tipo (1 Para, 2 CC, 3 CCO), nombre y
    direccion SMTP.
    """
    result = []
    for recipient in item.Recipients:
        address = ""
        try:
            address = recipient.PropertyAccessor.GetProperty(
                PR_SMTP_ADDRESS)
        except Exception:  # noqa: BLE001
            address = recipient.Address or ""
        result.append({"type": recipient.Type, "name": recipient.Name,
                       "address": address})
    return result


def _mail_key(item):
    try:
        message_id = item.PropertyAccessor.GetProperty(
            PR_INTERNET_MESSAGE_ID)
    except Exception:  # noqa: BLE001
        message_id = ""
    source = message_id or item.EntryID
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16], (
        message_id)


def _received(item):
    value = item.ReceivedTime
    return datetime.datetime(value.year, value.month, value.day,
                             value.hour, value.minute, value.second)


def _is_hidden(attachment):
    try:
        return bool(attachment.PropertyAccessor.GetProperty(
            PR_ATTACHMENT_HIDDEN))
    except Exception:  # noqa: BLE001
        return False


def _upload_mail(bucket, item, key, message_id, received, folder_path,
                 log_event):
    """Upload one mail: attachments first, then correo.json.
    ---
    Sube un correo: primero los adjuntos (los correos adjuntos van
    como .msg) y por ultimo la ficha. Devuelve (prefijo del cubo, si
    se ha subido ahora).
    """
    prefix = "%s/%s_%s" % (UPLOAD_PREFIX,
                           received.strftime("%Y%m%d-%H%M%S"), key)
    if bucket.blob("%s/%s" % (prefix, MAIL_JSON_NAME)).exists():
        return prefix, False
    attachments = []
    temp_dir = tempfile.mkdtemp(prefix="agente_correos_")
    try:
        used = set()
        for index in range(1, item.Attachments.Count + 1):
            attachment = item.Attachments.Item(index)
            name = _safe_name(attachment.FileName,
                              "adjunto_%d" % index)
            if name.lower() in used:
                base, ext = os.path.splitext(name)
                name = "%s_%d%s" % (base, index, ext)
            used.add(name.lower())
            path = os.path.join(temp_dir, name)
            attachment.SaveAsFile(path)
            blob_name = "%s/%s" % (prefix, name)
            bucket.blob(blob_name).upload_from_filename(path)
            attachments.append({
                "name": name, "original_name": attachment.FileName,
                "size": os.path.getsize(path),
                "hidden": _is_hidden(attachment),
                "type": attachment.Type, "blob": blob_name,
            })
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    body = item.Body or ""
    record = {
        "key": key,
        "message_id": message_id,
        "entry_id": item.EntryID,
        "outlook_folder": folder_path,
        "received": received.isoformat(),
        "sender_name": item.SenderName or "",
        "sender_address": _sender_address(item),
        "recipients": _recipients(item),
        "subject": item.Subject or "",
        "body": body[:MAX_BODY_CHARS],
        "body_truncated": len(body) > MAX_BODY_CHARS,
        "attachments": attachments,
        "read_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    bucket.blob("%s/%s" % (prefix, MAIL_JSON_NAME)).upload_from_string(
        json.dumps(record, ensure_ascii=False, indent=1),
        content_type="application/json; charset=utf-8",
    )
    log_event("Correo subido: %s — %s" % (
        received.strftime("%d/%m %H:%M"), record["subject"][:80]))
    return prefix, True


def scan_and_upload(client, settings, log_event):
    """Upload every mail of the folder received recently, once.
    ---
    Sube al cubo cada correo de la carpeta recibido en los ultimos
    LOOKBACK_DAYS que todavia no este. Escribe cada paso en el log y
    devuelve cuantos ha subido. Un fallo con un correo no para el
    resto: se reintenta en la siguiente revision.
    """
    state = load_state()
    bucket = client.bucket(BUCKET_NAME)
    folder = _open_folder(get_namespace(), settings)
    items = folder.Items
    items.Sort("[ReceivedTime]", True)
    cutoff = datetime.datetime.now() - datetime.timedelta(
        days=LOOKBACK_DAYS)
    uploaded = seen = 0
    item = items.GetFirst()
    while item is not None:
        if getattr(item, "Class", None) == OL_MAIL_ITEM:
            received = _received(item)
            if received < cutoff:
                break
            seen += 1
            key, message_id = _mail_key(item)
            if key not in state:
                try:
                    prefix, new = _upload_mail(
                        bucket, item, key, message_id, received,
                        folder.FolderPath, log_event)
                    state[key] = {"prefix": prefix,
                                  "received": received.isoformat()}
                    save_state(state)
                    uploaded += int(new)
                except Exception as error:  # noqa: BLE001
                    logger.exception("Fallo subiendo el correo %s", key)
                    log_event("Error con «%s»: %s (se reintenta)" % (
                        (item.Subject or "")[:60], error))
        item = items.GetNext()
    logger.info("Revision de %s: %d correo(s) de los ultimos %d dias, "
                "%d subidos.", folder.FolderPath, seen, LOOKBACK_DAYS,
                uploaded)
    return uploaded
