# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/management/commands/create_room_push_keys.py
"""
H37 (S138). Creates the VAPID keys of the room push notifications and
writes them to the project .env file, without printing the private key.

---

H37 (S138). Crea las claves VAPID de las notificaciones push de la sala
(curva P-256) y las añade al `.env` del proyecto
(`ROOM_PUSH_VAPID_PRIVATE_KEY`, `ROOM_PUSH_VAPID_PUBLIC_KEY`). Nunca
imprime la clave privada. Idempotente: si ya existen, no las toca
(cambiarlas dejaría sin avisos a todos los dispositivos ya activados).
Log propio en pantalla y en archivo a la vez (`--log-file`).
"""
import base64
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.management.base import BaseCommand
from dotenv import dotenv_values

from chat.push_service import PRIVATE_KEY_NAME, PUBLIC_KEY_NAME


def _b64url(data):
    """
    Base64url without padding.

    ---

    Base64url sin relleno, como piden las claves VAPID.
    """
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Command(BaseCommand):
    """
    Create the room push VAPID keys in .env.

    ---

    Crea las claves VAPID de la sala en el `.env`.
    """

    help = (
        "Crea las claves VAPID de las notificaciones push de la sala y "
        "las añade al .env (H37, S138)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file",
            required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run()

    def _run(self):
        env_path = settings.BASE_DIR / ".env"
        self._log("Inicio: claves VAPID de la sala en %s." % env_path)
        current = dotenv_values(env_path)
        if current.get(PRIVATE_KEY_NAME) and current.get(PUBLIC_KEY_NAME):
            self._log(
                "Ya existen %s y %s en el .env -- no se tocan."
                % (PRIVATE_KEY_NAME, PUBLIC_KEY_NAME)
            )
            self._log("Fin.")
            return
        key = ec.generate_private_key(ec.SECP256R1())
        private_raw = key.private_numbers().private_value.to_bytes(
            32, "big",
        )
        public_raw = key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        with open(env_path, "a", encoding="utf-8") as env:
            env.write(
                "\n# H37 (S138): claves VAPID de las push de la sala.\n"
                "%s=%s\n%s=%s\n" % (
                    PRIVATE_KEY_NAME, _b64url(private_raw),
                    PUBLIC_KEY_NAME, _b64url(public_raw),
                )
            )
        self._log(
            "Claves creadas y añadidas al .env (%s, %s). La privada no "
            "se muestra." % (PRIVATE_KEY_NAME, PUBLIC_KEY_NAME)
        )
        self._log("Fin.")
