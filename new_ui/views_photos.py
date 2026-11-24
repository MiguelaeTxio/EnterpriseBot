# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_photos.py
"""
Person photo in the new interface (S163).

---

La foto de la persona en la nueva interfaz (S163), copiada de la ficha
antigua (panel/views_documentation_h30.py, S134-S136):
- Acciones › «Del trabajador»: la foto, descargarla para plataformas
  (PNG de menos de 128 KB con su nombre, entera o el recuadro marcado),
  girarla, volver al modo automático y subir otra.
- «Esta fila» de un documento: usarlo como foto (imagen) o sacar de él
  la foto de carné (DNI, NIE, pasaporte, permiso, imagen).
- General › Acciones: volver a sacar la foto de los marcados.
Los cálculos son los de document_explorer.id_photo_service, como allí.
"""
import unicodedata

from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from document_explorer import id_photo_service as photos
from document_explorer.models import (
    DocumentIndexEntry, PersonIdentity, PersonIdPhoto,
)
from new_ui.mixins import SuperuserRequiredMixin
from spare_parts.gcs_service import download_bytes

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def platform_photo_name(person):
    """
    File name of the platform photo: SURNAMES_NAME.png, no accents.

    ---

    Nombre de la foto para plataforma: APELLIDOS_NOMBRE.png, sin tildes
    ni espacios.
    """
    parts = (person.first_surname, person.second_surname, person.given_name)
    text = "_".join(p for p in parts if p) or "FOTO_%s" % person.pk
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c if c.isalnum() else "_" for c in text.upper())
    return "%s.png" % "_".join(t for t in text.split("_") if t)


def _photo_bytes(person):
    """
    The person photo: the ID crop, or the image chosen as photo.

    ---

    La foto de la persona en bytes: el recorte de carné; si no, la
    imagen elegida como foto; None si no tiene.
    """
    id_photo = PersonIdPhoto.objects.filter(person=person).first()
    if id_photo is not None:
        return bytes(id_photo.image)
    entry = person.avatar_document
    if entry is not None and entry.name.lower().endswith(IMAGE_EXTENSIONS):
        return download_bytes(entry.bucket, entry.blob_name)
    return None


def _source_label(entry):
    label = entry.document_type.label if entry.document_type_id else ""
    return "su %s" % label if label else "un documento"


def _person_entry(person, entry_pk):
    return DocumentIndexEntry.objects.filter(
        pk=entry_pk if str(entry_pk).isdigit() else 0,
        domain_content_type=ContentType.objects.get_for_model(PersonIdentity),
        domain_object_id=person.pk, deleted_at__isnull=True,
        purged_at__isnull=True,
    ).select_related("document_type").first()


class PersonPhotoPanelView(SuperuserRequiredMixin, View):
    """
    GET: the photo block of «Del trabajador».

    ---

    GET: el bloque de la foto para Acciones › «Del trabajador».
    """

    def get(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        return render(request, "new_ui/_person_photo.html",
                      photo_panel_context(person))


def _useful_sources(person, id_photo):
    """
    The documents worth taking the photo from: in force, one per kind.

    ---

    De qué documentos tiene sentido sacar la foto (S163, 24/11, Miguel
    Ángel: "si alguien ha entrado aquí con 16 años y tiene 64, ¿cuántos
    DNIs podemos tener aquí para sacar fotos? ¿Y de qué sirve la foto
    del primero?"): solo los vigentes (no obsoletos ni caducados) y uno
    por tipo de documento y caducidad (el mismo DNI guardado dos veces
    sale una vez). Si no hay ninguno vigente, el último de cada tipo. El
    del que sale la foto actual, siempre.
    """
    from django.utils import timezone

    today = timezone.localdate()
    all_docs = list(photos.candidates(person).select_related(
        "document_type"))
    current = id_photo.source_id if id_photo else None
    useful = [d for d in all_docs if not d.is_obsolete
              and (d.expiry_date is None or d.expiry_date >= today)]
    if not useful:
        useful = all_docs
    out, seen = [], set()
    for doc in useful:
        key = (doc.document_type_id, doc.expiry_date)
        if doc.pk != current and key in seen:
            continue
        seen.add(key)
        out.append(doc)
    if not useful or useful is all_docs:
        # Sin vigentes: el último de cada tipo.
        kept, kinds = [], set()
        for doc in out:
            if doc.pk == current or doc.document_type_id not in kinds:
                kept.append(doc)
                kinds.add(doc.document_type_id)
        out = kept
    if current and all(d.pk != current for d in out):
        out += [d for d in all_docs if d.pk == current]
    return out


def photo_panel_context(person):
    """
    Context of the photo block (Acciones and the worker's Datos).

    ---

    Lo que pinta el bloque de la foto para plataformas y la revisión del
    contrato: en Acciones y, a la vista, en la ficha (Datos) del
    trabajador (S163, 23/11, Miguel Ángel: "la foto para plataformas
    [...] nos lo hemos cepillado por completo").
    """
    pk = person.pk
    id_photo = PersonIdPhoto.objects.filter(person=person).select_related(
        "source__document_type").first()
    photo_url = ""
    source = ""
    if id_photo is not None:
        photo_url = reverse("new_ui:person_photo", args=[pk])
        if id_photo.source_id:
            source = _source_label(id_photo.source)
        source = ("Puesta a mano" if id_photo.is_manual
                  else "Automática") + (" · de %s" % source
                                        if source else "")
    elif (person.avatar_document_id
          and person.avatar_document.name.lower().endswith(
              IMAGE_EXTENSIONS)):
        photo_url = reverse("new_ui:document_file",
                            args=[person.avatar_document_id])
        source = "Imagen elegida como foto"
    # S163: y la revisión del contrato vigente (antes, en su ficha).
    reviewer = person.contract_reviewed_by
    return {
        # S163 (24/11): lo de la ventana «Foto de perfil» antigua.
        "id_photo": id_photo,
        "avatar_pk": person.avatar_document_id if id_photo is None else None,
        "photo_sources": _useful_sources(person, id_photo),
        "person": person, "photo_url": photo_url, "source": source,
        "reviewed_at": person.contract_reviewed_at,
        "reviewed_by": (reviewer.user.get_full_name()
                        or reviewer.user.username) if reviewer else "",
    }


class PersonPlatformPhotoView(SuperuserRequiredMixin, View):
    """
    GET: the photo as a PNG under 128 KB, whole or the marked box.

    ---

    GET: la foto para plataforma: PNG de menos de 128 KB con el nombre
    de la persona; con x, y, w, h (fracciones de 0 a 1), solo el
    recuadro marcado (las plataformas piden que la cara ocupe casi
    todo).
    """

    def get(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        data = _photo_bytes(person)
        if data is None:
            return HttpResponse("Esta persona no tiene foto.", status=404,
                                content_type="text/plain; charset=utf-8")
        box = None
        raw = [request.GET.get(key, "") for key in ("x", "y", "w", "h")]
        if all(raw):
            try:
                box = tuple(float(value) for value in raw)
            except ValueError:
                return HttpResponse(
                    "Recuadro con formato inválido.", status=400,
                    content_type="text/plain; charset=utf-8")
        try:
            png = photos.platform_png(data, box=box)
        except photos.IdPhotoError as exc:
            return HttpResponse(str(exc), status=422,
                                content_type="text/plain; charset=utf-8")
        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = 'attachment; filename="%s"' % (
            platform_photo_name(person))
        return response


class PersonPhotoActionView(SuperuserRequiredMixin, View):
    """
    POST `action`: rotate, automatic, from a document, use an image.

    ---

    POST, según `action`:
    - left / right: girar un cuarto de vuelta (queda puesta a mano).
    - automatic: modo automático (sale del primer documento con cara).
    - extract + entry: sacar la foto de ese documento (puesta a mano).
    - use + entry: usar esa imagen como foto (se recorta la cara si la
      hay; si no, la imagen entera). El tipo del documento no cambia.
    """

    def post(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        action = request.POST.get("action", "")
        if action in ("left", "right"):
            data = _photo_bytes(person)
            if data is None:
                return _error("Esta persona no tiene foto.", 404)
            id_photo = PersonIdPhoto.objects.filter(person=person).first()
            source = id_photo.source if id_photo else person.avatar_document
            try:
                photos.save_rotated(person, data, action == "right",
                                    source=source)
            except photos.IdPhotoError as exc:
                return _error(str(exc), 422)
            return _ok("Foto girada a la %s." % (
                "derecha" if action == "right" else "izquierda"))
        if action == "automatic":
            entry = photos.set_automatic(person)
            if entry is None:
                return _error(
                    "Foto en modo automático, pero no se ha encontrado "
                    "ninguna cara en el DNI, NIE, pasaporte, permiso ni "
                    "imágenes de esta persona.", 422)
            return _ok("Foto en modo automático: sacada de %s." % (
                _source_label(entry)))
        if action == "extract":
            entry = photos.candidates(person).filter(
                pk=request.POST.get("entry") or 0).first()
            if entry is None:
                return _error(
                    "Ese documento no es un DNI, NIE, pasaporte, permiso "
                    "ni imagen de esta persona.")
            try:
                photos.extract_from_entry(person, entry, manual=True)
            except photos.IdPhotoError as exc:
                return _error(str(exc), 422)
            return _ok("Foto sacada de %s." % _source_label(entry))
        if action == "use":
            entry = _person_entry(person, request.POST.get("entry", ""))
            if entry is None:
                return _error("Ese documento no es de esta persona.")
            if not entry.name.lower().endswith(IMAGE_EXTENSIONS):
                return _error("Ese documento no es una imagen.")
            person.avatar_document = entry
            person.save(update_fields=["avatar_document"])
            try:
                photos.extract_from_entry(person, entry, manual=True)
                return _ok("Imagen puesta como foto (recortada a la cara).")
            except photos.IdPhotoError:
                PersonIdPhoto.objects.filter(person=person).delete()
                return _ok("Imagen puesta como foto (entera: no se ve "
                           "ninguna cara que recortar).")
        return _error("Acción no válida.")


class PersonPhotoQueueView(SuperuserRequiredMixin, View):
    """
    POST `selected`: send the marked persons back to automatic search.

    ---

    POST `selected`: las personas marcadas vuelven al modo automático
    (también las puestas a mano) y a la cola de la tarea de cada 15
    minutos.
    """

    def post(self, request):
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        if not ids:
            return _error("Marca primero a las personas.")
        count = photos.queue_recheck(ids)
        return _ok("%d persona(s) en cola para volver a sacar la foto "
                   "(la tarea pasa cada 15 minutos)." % count)


def is_photo_source(entry):
    """True if a photo can come out of this document."""
    return bool(entry.document_type_id
                and entry.document_type.code in photos.SOURCE_TYPES)


class PersonPlatformPhotoView(SuperuserRequiredMixin, View):
    """
    GET: the platform photo block of a person, for the viewer.

    ---

    GET: la foto para plataformas del trabajador (descargar entera o
    recortada, girar, modo automático, subir otra) para el visor que se
    abre al pulsar su foto en la ficha, como en la ficha antigua (S163,
    24/11, Miguel Ángel: "yo pincho la foto de Alberto y puedo hacer
    todas las acciones").
    """

    def get(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        return render(request, "new_ui/_platform_photo.html",
                      photo_panel_context(person))
