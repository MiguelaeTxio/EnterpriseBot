# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/mail_reader_agent/probar_lectura.py
"""Dry run: read an Outlook folder without uploading or touching it.
---
Prueba en seco (S156, PC de Miguel Angel): pide una carpeta de Outlook,
lee los correos de los ultimos dias como lo hara el agente y escribe en
pantalla y en `prueba_lectura.txt` (carpeta de datos del agente) lo que
ha leido de cada uno. No sube nada al cubo. Al final comprueba que el
numero de no leidos de la carpeta no ha cambiado.
"""
import datetime
import os
import sys

import pythoncom

from config import LOOKBACK_DAYS, OL_MAIL_ITEM, get_data_dir
from outlook_reader import (
    _mail_key, _received, _recipients, _sender_address, get_namespace,
)


def main():
    """Read and report, never modify.
    ---
    Lee e informa, sin modificar nada.
    """
    pythoncom.CoInitialize()
    log_path = os.path.join(get_data_dir(), "prueba_lectura.txt")
    with open(log_path, "a", encoding="utf-8") as log:
        def say(text):
            print(text, flush=True)
            log.write(text + "\n")
            log.flush()

        folder = get_namespace().PickFolder()
        if folder is None:
            say("Sin carpeta elegida.")
            return 1
        unread_before = folder.UnReadItemCount
        say("=== Prueba de lectura %s ===" % datetime.datetime.now()
            .strftime("%d/%m/%Y %H:%M:%S"))
        say("Carpeta: %s (no leídos: %d)" % (
            folder.FolderPath, unread_before))
        cutoff = datetime.datetime.now() - datetime.timedelta(
            days=LOOKBACK_DAYS)
        items = folder.Items
        items.Sort("[ReceivedTime]", True)
        count = 0
        item = items.GetFirst()
        while item is not None:
            if getattr(item, "Class", None) == OL_MAIL_ITEM:
                received = _received(item)
                if received < cutoff:
                    break
                count += 1
                key, message_id = _mail_key(item)
                names = [item.Attachments.Item(i).FileName
                         for i in range(1, item.Attachments.Count + 1)]
                to = ", ".join(r["address"] or r["name"]
                               for r in _recipients(item))
                say("[%d] %s | %s <%s>" % (
                    count, received.strftime("%d/%m/%Y %H:%M"),
                    item.SenderName, _sender_address(item)))
                say("    Para: %s" % to)
                say("    Asunto: %s" % item.Subject)
                say("    Adjuntos: %s" % ("; ".join(names) or "-"))
                say("    Cuerpo: %d caracteres | huella %s | %s" % (
                    len(item.Body or ""), key,
                    "Message-ID" if message_id else "EntryID"))
            item = items.GetNext()
        unread_after = folder.UnReadItemCount
        say("Correos leídos de los últimos %d días: %d" % (
            LOOKBACK_DAYS, count))
        say("No leídos antes: %d, después: %d -> %s" % (
            unread_before, unread_after,
            "SIN CAMBIOS" if unread_before == unread_after
            else "HAN CAMBIADO"))
        say("Resultado también en: %s" % log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
