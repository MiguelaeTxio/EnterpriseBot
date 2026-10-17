# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clockin_test.py
"""
Offline clock-in proof of concept (H24, S129, before roadmap point 3).

Miguel Ángel wants to see working, on a real Android phone and a real
iPhone, what the offline web clock-in would do before choosing how
point 3 is built: open the page once with coverage, then in airplane
mode (GPS on) press the button; the phone keeps the time of the press
and the GPS position and sends them when the connection returns. The
server answers with the time it received them, so the page itself
shows the gap.

Nothing is stored in the database: the receive endpoint only answers
and writes one log line (WARNING level, so it reaches the web app's
error log, which the model reads through the read-only relay). It is
public and CSRF-exempt on purpose: a queued offline press is sent
later, possibly without a valid session or token, and the endpoint
changes nothing. The whole module is a test and will be removed when
point 3 is built.

---

Prueba de fichaje sin cobertura (H24, S129, antes del punto 3 de la
hoja de ruta).

Miguel Ángel quiere ver funcionando, en un Android y un iPhone reales,
lo que haría la web de fichaje sin cobertura antes de decidir cómo se
construye el punto 3: abrir la página una vez con cobertura y después,
en modo avión (con el GPS activado), pulsar el botón; el móvil guarda
la hora de la pulsación y la posición GPS y las envía al volver la
conexión. El servidor responde con la hora a la que las recibió, así
que la propia página muestra la diferencia.

No se guarda nada en la base de datos: el endpoint de recepción solo
responde y escribe una línea de log (nivel WARNING, para que llegue al
log de errores de la web, que el modelo lee con el relevo de solo
lectura). Es público y sin CSRF a propósito: una pulsación guardada sin
cobertura se envía más tarde, quizá sin sesión ni token válidos, y el
endpoint no cambia nada. Todo el módulo es una prueba y se retirará al
construir el punto 3.
"""
import json
import logging
from pathlib import Path

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

_SW_PATH = (
    Path(__file__).resolve().parent / "static_src" / "clockin_test_sw.js"
)
_MAX_BODY = 4096


@never_cache
def page(request):
    """
    GET: the test page (cached by the service worker for offline use).
    ---
    GET: la página de prueba (la guarda el service worker para usarla
    sin cobertura).
    """
    return render(request, "hr_calendar/clockin_test.html")


@never_cache
def service_worker(request):
    """
    GET: the service worker, served inside /fichaje-prueba/ so its
    scope is exactly that path.
    ---
    GET: el service worker, servido dentro de /fichaje-prueba/ para que
    su ámbito sea exactamente esa ruta.
    """
    response = HttpResponse(
        _SW_PATH.read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/fichaje-prueba/"
    return response


@never_cache
def manifest(request):
    """
    GET: web app manifest, so the page can be added to the home screen.
    ---
    GET: manifiesto, para poder añadir la página a la pantalla de
    inicio como una app.
    """
    data = {
        "name": "Fichaje (prueba) — Grupo Álvarez",
        "short_name": "Fichaje prueba",
        "start_url": "/fichaje-prueba/",
        "scope": "/fichaje-prueba/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0d6efd",
        "orientation": "portrait",
        "icons": [
            {"src": "/static/panel/img/albaran_icon_192.png",
             "sizes": "192x192", "type": "image/png"},
            {"src": "/static/panel/img/albaran_icon_512.png",
             "sizes": "512x512", "type": "image/png"},
        ],
    }
    return HttpResponse(
        json.dumps(data, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@csrf_exempt
@require_POST
def receive(request):
    """
    POST (JSON): one press; answers with the server receive time.
    ---
    POST (JSON): una pulsación; responde con la hora de recepción del
    servidor y la diferencia con la hora de la pulsación. No guarda
    nada en BD: una línea de log por pulsación.
    """
    if len(request.body) > _MAX_BODY:
        return JsonResponse({"error": "Petición demasiado grande."},
                            status=400)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON no válido."}, status=400)
    received_at = timezone.now()
    pressed_at = parse_datetime(str(payload.get("pressed_at", "")))
    gap = None
    if pressed_at is not None and timezone.is_aware(pressed_at):
        gap = round((received_at - pressed_at).total_seconds())
    tester = str(payload.get("tester", ""))[:60]
    logger.warning(
        "# [fichaje_prueba] id=%s quien=%r tipo=%s pulsado=%s recibido=%s "
        "diferencia_s=%s lat=%s lon=%s precision_m=%s gps_ms=%s "
        "gps_error=%r envio=%s ua=%r",
        str(payload.get("id", ""))[:40], tester,
        str(payload.get("kind", ""))[:10],
        payload.get("pressed_at"), received_at.isoformat(), gap,
        _number(payload.get("lat")), _number(payload.get("lon")),
        _number(payload.get("accuracy")), _number(payload.get("gps_ms")),
        str(payload.get("gps_error", ""))[:120],
        str(payload.get("sent_by", ""))[:40],
        request.META.get("HTTP_USER_AGENT", "")[:160],
    )
    return JsonResponse({
        "received_at": received_at.isoformat(),
        "gap_seconds": gap,
    })
