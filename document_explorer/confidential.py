# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/confidential.py
"""
Confidential documents (S147): payslips only for the worker and the
person who sends them.

---

Documentos confidenciales (S147). Miguel Ángel: "un trabajador solicita
su nómina y el [...] encargado de las nóminas se la envía [...] y nadie
puede ver ese documento exceptuando el administrador que le envía y el
trabajador que la recibe".

- Un tipo marcado `DocumentTypeCatalog.is_confidential` (NOMINA) hace
  confidencial cada documento que se suba de ahí en adelante: se guarda
  cifrado en el cubo (Fernet, llave CONFIDENTIAL_DOCS_KEY del .env), sin
  lectura automática (OCR), y la fila apunta quién lo envió.
- Lo abren solo el trabajador (su usuario del panel) y quien lo envió.
  Nadie más, tampoco un administrador: ve que existe, no el contenido.
- Cualquier otro camino que lea el archivo del cubo recibe el cifrado,
  ilegible: lo que no pase por aquí no puede enseñarlo.
- Cada intento de abrirlo queda en ConfidentialAccessLog.
"""
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

KEY_ENV = "CONFIDENTIAL_DOCS_KEY"
DENIED = ("Documento confidencial: solo lo pueden abrir el trabajador y "
          "quien se lo envió.")
NO_KEY = ("No se puede guardar un documento confidencial: falta la llave "
          "de cifrado en el servidor. Avisa a los administradores del "
          "sistema.")


class ConfidentialError(Exception):
    """
    A confidential document cannot be stored or opened.
    ---
    No se puede guardar o abrir un documento confidencial (mensaje para
    quien lo intenta).
    """


def _fernet():
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise ConfidentialError(NO_KEY)
    return Fernet(key.encode())


def encrypt(data):
    """
    The bytes encrypted with the server key.
    ---
    Los bytes cifrados con la llave del servidor.
    """
    return _fernet().encrypt(data)


def decrypt(data):
    """
    The original bytes of an encrypted document.
    ---
    Los bytes originales de un documento cifrado.
    """
    try:
        return _fernet().decrypt(data)
    except InvalidToken as exc:
        raise ConfidentialError(
            "No se ha podido descifrar el documento.") from exc


def worker_user_id(entry):
    """
    The panel user of the worker the document belongs to, or None.
    ---
    El usuario del panel del trabajador dueño del documento, o None.
    """
    from document_explorer.models import PersonIdentity

    if entry.domain_content_type.model_class() is not PersonIdentity:
        return None
    return PersonIdentity.objects.filter(
        pk=entry.domain_object_id,
    ).values_list("company_user_id", flat=True).first()


def can_open(entry, company_user):
    """
    True if this user may see the document's content.
    ---
    True si este usuario puede ver el contenido: cualquier documento no
    confidencial (el resto de permisos los pone cada vista), y uno
    confidencial solo su trabajador y quien lo envió.
    """
    if not entry.is_confidential:
        return True
    if company_user is None:
        return False
    return company_user.pk in (entry.confidential_sender_id,
                               worker_user_id(entry))


def open_bytes(entry, company_user):
    """
    The readable bytes of a document for this user.
    ---
    Los bytes legibles de un documento para este usuario: los de
    siempre si no es confidencial; si lo es, solo para el trabajador o
    quien lo envió (descifrados) y queda el intento registrado. Si no
    puede, ConfidentialError(DENIED).
    """
    from spare_parts.gcs_service import download_bytes

    if not entry.is_confidential:
        return download_bytes(entry.bucket, entry.blob_name)
    from document_explorer.models import ConfidentialAccessLog

    allowed = can_open(entry, company_user)
    ConfidentialAccessLog.objects.create(
        entry=entry, company_user=company_user, allowed=allowed)
    if not allowed:
        logger.warning("[confidencial] acceso denegado entry=%s cu=%s",
                       entry.pk, getattr(company_user, "pk", None))
        raise ConfidentialError(DENIED)
    return decrypt(download_bytes(entry.bucket, entry.blob_name))


def denied_response(message=DENIED):
    """
    The page shown to someone who may not open the document.
    ---
    La página para quien no puede abrir el documento (403).
    """
    from django.http import HttpResponseForbidden

    return HttpResponseForbidden(
        "<html><head><meta name='viewport' content='width=device-width'>"
        "</head><body style='font-family:system-ui,sans-serif;padding:24px'>"
        "<h3>&#128274; %s</h3></body></html>" % message,
        content_type="text/html; charset=utf-8",
    )


def file_response(entry, company_user, attachment=False):
    """
    The HTTP response with a document for this user.
    ---
    La respuesta HTTP con el documento (en línea o como descarga) para
    este usuario, o la página de acceso denegado.
    """
    import mimetypes
    from urllib.parse import quote

    from django.http import HttpResponse

    try:
        data = open_bytes(entry, company_user)
    except ConfidentialError as exc:
        return denied_response(str(exc))
    content_type = (entry.content_type
                    or mimetypes.guess_type(entry.name)[0]
                    or "application/octet-stream")
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = "%s; filename*=UTF-8''%s" % (
        "attachment" if attachment else "inline", quote(entry.name))
    response["Cache-Control"] = "private, no-store"
    return response
