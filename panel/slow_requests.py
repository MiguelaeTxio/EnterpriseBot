# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/slow_requests.py
"""
S153. Logs slow requests with their database queries, to find what
makes a page slow in production.

---

S153. Miguel Ángel: "tarda muchísimo en cargar [...] a ver cómo hacemos
las consultas". El log de accesos de la web muestra, por ejemplo, que
Personal tarda una mediana de 14 s y sus resultados 6 s, pero no por
qué. Este middleware cuenta y cronometra las consultas a la base de
datos de cada petición (connection.execute_wrapper, sin DEBUG) y,
cuando una petición tarda más de SLOW_SECONDS, apunta en
logs/slow_requests.log: ruta, tiempo total, tiempo y número de
consultas, y las consultas que más se repiten (las de "una por fila").
Coste por petición: un contador; solo escribe en las lentas.
"""
import collections
import logging
import os
import re
import time

from django.conf import settings
from django.db import connection

# S153: 1 s para encontrar también las pestañas de 1-3 s.
SLOW_SECONDS = 1.0
_TOP = 6
_NUMBERS = re.compile(r"\b\d+\b")
_LOG_PATH = os.path.join(settings.BASE_DIR, "logs", "slow_requests.log")

logger = logging.getLogger("panel.slow_requests")
if not logger.handlers:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
        _handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(_handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    except OSError:
        pass


class _QueryTimer:
    """
    execute_wrapper that counts and times the queries.
    ---
    Cuenta y cronometra las consultas; agrupa el SQL sin números para
    ver las que se repiten.
    """

    def __init__(self):
        self.count = 0
        self.seconds = 0.0
        self.shapes = collections.Counter()
        self.shape_seconds = collections.Counter()

    def __call__(self, execute, sql, params, many, context):
        start = time.monotonic()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed = time.monotonic() - start
            self.count += 1
            self.seconds += elapsed
            shape = _NUMBERS.sub("N", sql or "")[:160]
            self.shapes[shape] += 1
            self.shape_seconds[shape] += elapsed


class SlowRequestLogMiddleware:
    """
    Writes slow requests (> SLOW_SECONDS) to logs/slow_requests.log.
    ---
    Apunta las peticiones lentas con el detalle de sus consultas.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timer = _QueryTimer()
        start = time.monotonic()
        with connection.execute_wrapper(timer):
            response = self.get_response(request)
        total = time.monotonic() - start
        if total >= SLOW_SECONDS:
            try:
                user = getattr(request.user, "username", "")
            except Exception:
                user = ""
            lines = [
                "LENTA %.2fs %s %s usuario=%s consultas=%d bd=%.2fs "
                "resto=%.2fs" % (
                    total, request.method, request.get_full_path()[:200],
                    user, timer.count, timer.seconds, total - timer.seconds),
            ]
            shown = set()
            for shape, times in timer.shapes.most_common(_TOP):
                shown.add(shape)
                lines.append("    %4dx %.2fs %s" % (
                    times, timer.shape_seconds[shape], shape))
            # S157: también las más lentas aunque no se repitan (Personal
            # del 18/11: 20 s de BD sin que ninguna repetida lo explicara).
            for shape, seconds in timer.shape_seconds.most_common(_TOP):
                if shape in shown or seconds < 0.25:
                    continue
                lines.append("    %4dx %.2fs LENTA %s" % (
                    timer.shapes[shape], seconds, shape))
            logger.info("\n".join(lines))
        return response
