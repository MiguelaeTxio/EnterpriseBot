"""
Shared paths, constants and logging for the Outlook voice demo agent.

---

Rutas, constantes y log compartidos del agente demo de voz para
Outlook.
"""

import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'demo_data'
LOG_PATH = BASE_DIR / 'demo_agent.log'
WAV_PATH = DATA_DIR / 'last_message.wav'

RECIPIENT = 'nummenor@gmail.com'
SUBJECT = 'prueba'

GEMINI_MODEL = 'gemini-3.5-flash'
GEMINI_LOCATION = 'global'
SAMPLE_RATE = 16000
WATCH_INTERVAL_SECONDS = 1.0
OUTLOOK_EXES = ('outlook.exe', 'olk.exe')
DEFAULT_KEY_PATH = (
    Path(os.environ.get('LOCALAPPDATA', ''))
    / 'EnterpriseBot' / 'H28MigrationAgent' / 'service_account_key.json'
)


def log(message):
    """
    Writes a timestamped line to screen and to the agent log file.

    ---

    Escribe una linea con hora en pantalla y en el log del agente.
    """
    DATA_DIR.mkdir(exist_ok=True)
    line = '[%s] %s' % (datetime.now().strftime('%H:%M:%S'), message)
    print(line, flush=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as handle:
        handle.write(line + '\n')
        handle.flush()
