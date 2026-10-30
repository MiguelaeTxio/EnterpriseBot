# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/purge_test_person_s141.py
"""
S141. Deletes, for good, one test person and every trace of her.

---

S141. Borra de verdad una persona de prueba y todo rastro suyo. Miguel
Ángel: "Encarnación Cervera Romero [...] fue un usuario de prueba que
puse para probar el tema de la sala de asistencia [...] la eliminamos
por completo del sistema como si no hubiera entrado nunca", "hasta en
el cubo".

Qué borra (solo lo de esa persona, nunca por parecido):
- En el cubo: todo objeto (y todas sus versiones) cuya ruta contenga
  su carpeta o su DNI, los archivos de su ficha y los adjuntos de sus
  mensajes en la sala.
- En la BD: sus entradas del índice del explorador (y avisos y líneas
  de registro de operaciones que las nombran), su foto de carné, sus
  mensajes y su pertenencia a la sala, las sesiones de WhatsApp de su
  móvil de prueba y su ficha (lo demás que cuelga de la ficha se va con
  ella).

Sin --apply solo lista lo que haría. Exige --person-id y --dni a la vez,
para no borrar a otra persona por un número equivocado.
"""
import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

BUCKET = "cgs_grupo_alvarez"


class Command(BaseCommand):
    help = ("Borra de verdad una persona de prueba y todo rastro suyo, "
            "también en el cubo (S141). Sin --apply solo lista.")

    def add_arguments(self, parser):
        parser.add_argument("--person-id", type=int, required=True)
        parser.add_argument("--dni", required=True)
        parser.add_argument("--phone", default="",
                            help="9 cifras del móvil de prueba (sesiones "
                                 "de WhatsApp a borrar)")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        line = "[%s] %s" % (
            datetime.datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._run(options)

    def _run(self, options):
        from chat.models import ChatMessage, ChatRoomMember
        from document_explorer.models import (
            DataOperationLogEntry, DocumentIndexEntry, PersonIdentity,
            PersonIdPhoto,
        )
        from document_management.models import DocumentAlert
        from whatsapp.models import WhatsAppSession

        apply = options["apply"]
        mode = "BORRANDO" if apply else "SIMULACIÓN (sin --apply)"
        self._log("Inicio -- %s." % mode)
        person = PersonIdentity.objects.filter(
            pk=options["person_id"]).first()
        dni = (options["dni"] or "").strip().upper()
        if person is None or (person.dni or "").strip().upper() != dni:
            self._log("ERROR: la persona %s no existe o su DNI no es %s." % (
                options["person_id"], dni))
            raise CommandError("Persona y DNI no coinciden.")
        folder = (person.folder_path or "").rstrip("/").split("/")[-1]
        digits = "".join(c for c in dni if c.isdigit())
        self._log("Persona %d: %s %s %s, DNI %s, carpeta %s." % (
            person.pk, person.given_name, person.first_surname,
            person.second_surname, dni, person.folder_path))
        if person.company_user_id:
            self._log("ATENCIÓN: tiene usuario del panel #%d; no se borra "
                      "aquí." % person.company_user_id)

        # ---- Entradas del índice del explorador ----------------------
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        name_q = Q()
        for token in [t for t in (folder, digits) if len(t) >= 8]:
            name_q |= Q(blob_name__icontains=token)
        entries = list(DocumentIndexEntry.objects.filter(
            Q(domain_content_type=person_ct, domain_object_id=person.pk)
            | name_q,
        ))
        entry_ids = [e.pk for e in entries]
        for entry in entries:
            self._log("Índice #%d: %s/%s" % (entry.pk, entry.bucket,
                                             entry.blob_name))
        entry_ct = ContentType.objects.get_for_model(DocumentIndexEntry)
        alerts = DocumentAlert.objects.filter(
            Q(content_type=entry_ct, object_id__in=entry_ids)
            | Q(content_type=person_ct, object_id=person.pk),
        )
        text_q = Q(index_entry_id__in=entry_ids)
        for token in [t for t in (folder, digits) if len(t) >= 8]:
            for field in ("blob_name", "parent_path", "name",
                          "previous_name", "detail"):
                text_q |= Q(**{field + "__icontains": token})
        oplog = DataOperationLogEntry.objects.filter(text_q)
        photos = PersonIdPhoto.objects.filter(person=person)
        messages = ChatMessage.objects.filter(author=person)
        members = ChatRoomMember.objects.filter(person=person)
        phone = "".join(c for c in options["phone"] if c.isdigit())[-9:]
        sessions = (WhatsAppSession.objects.filter(
            phone_number__endswith=phone) if len(phone) == 9
            else WhatsAppSession.objects.none())
        for session in sessions:
            self._log("Sesión de WhatsApp #%d %s (%s, %d mensajes)." % (
                session.pk, session.phone_number,
                session.session_start.strftime("%d/%m/%Y"),
                session.messages.count()))
        self._log("BD: índice %d, avisos %d, registro de operaciones %d, "
                  "fotos %d, mensajes de sala %d, sala %d, sesiones "
                  "WhatsApp %d, ficha 1." % (
                      len(entries), alerts.count(), oplog.count(),
                      photos.count(), messages.count(), members.count(),
                      sessions.count()))

        # ---- Cubo ----------------------------------------------------
        from spare_parts.gcs_service import get_storage_client

        client = get_storage_client()
        bucket = client.bucket(BUCKET)
        bucket.reload()
        policy = getattr(bucket, "soft_delete_policy", None)
        seconds = getattr(policy, "retention_duration_seconds", None)
        self._log("Cubo %s: versionado %s, retención de borrados %s s." % (
            BUCKET, bucket.versioning_enabled, seconds))
        names = {e.blob_name for e in entries
                 if e.bucket == BUCKET and e.entry_kind != "FOLDER"}
        names |= {m.attachment_blob for m in messages if m.attachment_blob}
        for token in [t for t in (folder, digits) if len(t) >= 8]:
            for blob in client.list_blobs(
                    BUCKET, match_glob="**%s**" % token, versions=True):
                names.add(blob.name)
        blobs = []
        for name in sorted(names):
            for blob in client.list_blobs(BUCKET, prefix=name,
                                          versions=True):
                if blob.name == name:
                    blobs.append(blob)
        for blob in blobs:
            self._log("Cubo: %s (versión %s, %s bytes)." % (
                blob.name, blob.generation, blob.size))
        self._log("Cubo: %d objeto(s)/versión(es)." % len(blobs))

        if not apply:
            self._log("Fin de la simulación: no se ha borrado nada.")
            return

        deleted_blobs = 0
        for blob in blobs:
            bucket.blob(blob.name, generation=blob.generation).delete()
            deleted_blobs += 1
        self._log("Cubo: %d borrado(s)." % deleted_blobs)
        with transaction.atomic():
            counts = {
                "avisos": alerts.delete()[0],
                "registro": oplog.delete()[0],
                "fotos": photos.delete()[0],
                "mensajes": messages.delete()[0],
                "sala": members.delete()[0],
                "whatsapp": sessions.delete()[0],
                "indice": DocumentIndexEntry.objects.filter(
                    pk__in=entry_ids).delete()[0],
            }
            counts["ficha"] = PersonIdentity.objects.filter(
                pk=person.pk).delete()[0]
        self._log("BD borrado: %s." % ", ".join(
            "%s %d" % item for item in counts.items()))
        self._log("Fin.")
