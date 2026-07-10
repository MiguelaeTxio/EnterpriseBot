# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/mimoo_updates/views.py
"""
Views for mimoo_updates.

Two GET endpoints, both gated by a random token embedded in the URL
path itself (not a query param, not a header) -- checked with
hmac.compare_digest() to avoid timing side-channels. A mismatched or
missing token returns Http404, identical to a URL that doesn't exist
at all -- never a 403, which would confirm the route is real to
anyone probing it.

No database model, no migrations: both endpoints only read fixed
files from disk, whose paths come from settings (backed by .env, see
enterprise_core/settings.py).
---
Vistas de mimoo_updates.

Dos endpoints GET, ambos protegidos por un token aleatorio embebido
en la propia ruta de la URL (no un query param, no una cabecera) --
verificado con hmac.compare_digest() para evitar canales laterales de
tiempo. Un token ausente o incorrecto devuelve Http404, identico a
una URL que directamente no existe -- nunca un 403, que confirmaria
a quien la esta probando que la ruta es real.

Sin modelo de base de datos, sin migraciones: ambos endpoints solo
leen archivos fijos desde disco, cuyas rutas vienen de settings
(respaldadas por .env, ver enterprise_core/settings.py).
"""
import hmac
import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def _token_is_valid(token: str) -> bool:
    """
    Constant-time comparison against the configured token. Returns
    False (never raises) if the token isn't configured at all, so a
    missing .env value fails closed instead of open.
    ---
    Comparacion en tiempo constante contra el token configurado.
    Devuelve False (nunca lanza) si el token no esta configurado en
    absoluto, para que un valor de .env ausente falle cerrado en vez
    de abierto.
    """
    expected = getattr(settings, "MIMOO_UPDATES_TOKEN", None)
    if not expected:
        return False
    return hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


@require_GET
@never_cache
def manifest_view(request, token: str):
    """
    Serves MIMOO_MANIFEST_PATH as-is (application/json), so MiMoo's
    own build workflow controls the exact contents (versionCode,
    versionName, apkUrl) -- this view has no opinion on that format,
    it only gates and streams the file.
    ---
    Sirve MIMOO_MANIFEST_PATH tal cual (application/json), para que
    el propio workflow de compilacion de MiMoo controle el contenido
    exacto (versionCode, versionName, apkUrl) -- esta vista no tiene
    ninguna opinion sobre ese formato, solo protege y entrega el
    archivo.
    """
    if not _token_is_valid(token):
        raise Http404()

    manifest_path = getattr(settings, "MIMOO_MANIFEST_PATH", None)
    if not manifest_path or not os.path.isfile(manifest_path):
        raise Http404()

    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()

    return HttpResponse(content, content_type="application/json; charset=utf-8")


@require_GET
@never_cache
def apk_view(request, token: str):
    """
    Streams MIMOO_APK_PATH as a download. FileResponse handles
    chunked streaming on its own -- no need to read the whole APK
    into memory.
    ---
    Transmite MIMOO_APK_PATH como descarga. FileResponse gestiona el
    streaming por trozos por si solo -- no hace falta cargar el APK
    entero en memoria.
    """
    if not _token_is_valid(token):
        raise Http404()

    apk_path = getattr(settings, "MIMOO_APK_PATH", None)
    if not apk_path or not os.path.isfile(apk_path):
        raise Http404()

    return FileResponse(
        open(apk_path, "rb"),
        as_attachment=True,
        filename="MiMoo.apk",
        content_type="application/vnd.android.package-archive",
    )
