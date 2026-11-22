# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_personnel.py
"""
Hiring, termination and re-activation of workers, new interface (S163).

---

Alta, baja y reactivación de trabajadores en la nueva interfaz (S163),
copiado tal cual de panel/views_documentation_h30.py
(PersonalIntakeExtractView, PersonalCreateView, PersonalTerminateView,
PersonalReactivateView y sus ayudantes) y de
panel/views_personal_local_download.py; renombrado y sin llamar a la
interfaz antigua. Desde Personal › Acciones:
- Alta guiada por documentos: se suben (hasta 20), se leen los datos y
  el supervisor confirma o corrige el borrador; si la persona existe de
  baja, el alta la reactiva.
- Baja (rescisión de contrato) y reactivar (deshacer o recontratar) de
  los marcados.
Las respuestas llevan además `message` para el aviso de Acciones.
"""
import base64
import hashlib
import logging
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View

from document_explorer import (
    local_download_service, naming_service, personal_intake_service,
    postal_code_service,
)
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentTypeCatalog, PersonIdentity, path_digest,
)
from document_management.models import DocumentSubstitutionLog
from document_management.vigencia_service import (
    DocumentSnapshot, evaluate_substitution,
)
from ivr_config.models import Company, Section
from new_ui.docs_core import BUCKET, COMPANY_FILTER_CHOICES
from new_ui.mixins import SuperuserRequiredMixin as DocsUploadAccessMixin

logger = logging.getLogger(__name__)

ALTA_COMPANY_CHOICES = [
    (raws[0], label) for slug, label, raws in COMPANY_FILTER_CHOICES
    if slug != "sin_empresa"
]


class PersonnelIntakeExtractView(DocsUploadAccessMixin, View):
    """
    H31 (S100), Bloque 1 -- PASO 1 del alta guiada por documentación.
    Recibe 1-N documentos subidos (DNI/contrato/reconocimiento médico,
    campo `documents`, multipart), extrae sus datos con
    `personal_intake_service` y devuelve un borrador ya combinado --
    NUNCA crea nada todavía. El supervisor confirma o corrige ese
    borrador en el paso 2 (`PersonalCreateView`), que es quien de
    verdad escribe en BD y sube los archivos a GCS.

    Puramente síncrono, sin persistencia intermedia -- si el
    supervisor cierra el modal sin confirmar, no queda ningún rastro
    en BD (ver anexo H31, corrección de preguntas 3/4: nada de cola de
    pendientes).
    """

    def post(self, request):
        import concurrent.futures

        files = request.FILES.getlist("documents")
        if not files:
            return JsonResponse(
                {"ok": False, "error": "No se ha subido ningún documento."},
                status=400,
            )
        # H31 (S100), confirmado por Miguel Ángel: 20 documentos cubren
        # prácticamente todo un alta real -- el resto se sube después
        # desde la ficha ya creada, por la vía normal (sin este tope).
        if len(files) > 20:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Máximo 20 documentos en el alta -- el resto "
                             "súbelos después desde la ficha ya creada.",
                },
                status=400,
            )

        # H31 (S100), incidente real: procesar los documentos uno a
        # uno convertía el tiempo total en la SUMA de los tiempos de
        # cada uno -- con 15 documentos y algún 429/504 transitorio de
        # Vertex AI en el camino (reintento real, ver
        # personal_intake_service._RETRY_DELAY_SECONDS), la espera en
        # el modal llegó a acercarse a los 3 minutos. Las llamadas son
        # de red (Cloud Vision + Gemini), no de CPU, así que
        # paralelizarlas con hilos es seguro (el GIL no bloquea E/S) y
        # el limitador de tasa compartido (`acquire_gemini_slot`, con
        # su propio `threading.Lock`) ya está pensado para que varias
        # llamadas concurrentes lo respeten sin pisarse. El tiempo
        # total pasa a ser el del documento más lento, no la suma de
        # todos.
        file_bytes = [(f.name, f.content_type, f.read()) for f in files]
        results_by_index = [None] * len(file_bytes)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = {
                pool.submit(
                    personal_intake_service.extract_one_document,
                    data, content_type or "application/octet-stream",
                    filename=name,
                ): idx
                for idx, (name, content_type, data) in enumerate(file_bytes)
            }
            for future in concurrent.futures.as_completed(futures):
                results_by_index[futures[future]] = future.result()

        extractions = []
        per_file = []
        filenames = []
        for (name, _content_type, _data), result in zip(
            file_bytes, results_by_index
        ):
            extractions.append(result)
            filenames.append(name)
            per_file.append(
                {
                    "filename": name,
                    "document_type_code": result.get(
                        "document_type_code", "DESCONOCIDO"
                    ),
                    "confidence": result.get("confidence", ""),
                    "expiry_hint": result.get("expiry_hint", ""),
                    "issue_hint": result.get("issue_hint", ""),
                    "error": result.get("error"),
                }
            )

        # H31 (S101), Miguel Ángel, verbatim: "estamos indicando números
        # de documentos y no nombres de documentos [...] eso no sirve
        # absolutamente para nada" -- con 10-15 documentos en el mismo
        # lote, "Documento 7" no le dice al supervisor cuál de sus
        # archivos hay que revisar; el nombre real sí.
        merged = personal_intake_service.merge_person_draft(
            extractions, filenames=filenames,
        )
        draft = merged["draft"]

        # H31 (S101), Miguel Ángel, verbatim: "el hecho de que los
        # documentos que dispongan de número de DNI, ese número sea
        # coincidente para todos y rechazar el documento en minoría."
        # `merge_person_draft` ya decidió cuáles son -- aquí se
        # materializa el rechazo forzando su `document_type_code` a
        # DESCONOCIDO, que es justo lo que `_store_documents` ya
        # descarta por la vía normal (ver comentario de esa función).
        # El aviso de por qué se descarta cada uno ya viene en
        # merged["warnings"], con el nombre del archivo.
        for rejected_idx in merged.get("rejected_indices", []):
            per_file[rejected_idx]["document_type_code"] = "DESCONOCIDO"

        # H31 (S100), incidente real: el procesamiento en paralelo de
        # arriba puede tardar bastantes segundos sin tocar la BD para
        # nada (todo el tiempo es red hacia Gemini/Cloud Vision). La
        # conexión de BD que Django abrió al entrar en la vista
        # (autenticación) se queda inactiva mientras tanto, y MySQL
        # (con su propio `wait_timeout` real de PythonAnywhere) puede
        # cerrarla por su cuenta antes de que se vuelva a usar aquí --
        # error real visto en producción: `MySQLdb.OperationalError:
        # (4031, 'The client was disconnected by the server because
        # of inactivity...')`. `close_old_connections()` descarta esa
        # conexión ya inválida y fuerza una reconexión limpia en la
        # siguiente consulta, sin que el supervisor vea nada raro.
        from django.db import close_old_connections
        close_old_connections()

        # H31 (S100), incidente real de la propia sesión: Miguel Ángel
        # probó el alta con su propio DNI (ya dado de alta antes) y el
        # sistema no avisó -- dejó seguir hasta el paso de confirmación
        # sin decir nada, pese a haber leído el DNI correctamente.
        # Corregido: la comprobación de duplicado se hace aquí, nada
        # más leer los documentos, ANTES de mostrar el formulario de
        # confirmación -- nunca al final. Se devuelven igualmente los
        # datos ya leídos (draft/per_file), para que el supervisor vea
        # qué ha leído el sistema antes de cerrar el aviso.
        normalized_dni = personal_intake_service.normalize_dni(draft["dni"])
        existing_person = (
            PersonIdentity.objects.filter(dni=normalized_dni).first()
            if normalized_dni else None
        )
        # H31 (S101), Miguel Ángel, verbatim: "si no hay ningún DNI, ni
        # se puede extraer ningún número de identificación, debemos
        # avisar del error y no contaminar la base de datos con datos
        # potencialmente erróneos." Sin ningún documento del lote que
        # traiga el DNI/NIE (de cualquier tipo, ver
        # `merge_person_draft` -- ya no hace falta que sea el propio
        # carnet), el supervisor tendría que escribirlo entero a mano
        # sin nada que lo verifique -- justo el escenario real que
        # detectó Miguel Ángel: toda su documentación real yendo a
        # parar a una identidad inventada. Se corta aquí, antes de
        # mostrar el formulario de confirmación, nunca después.
        if not normalized_dni:
            return JsonResponse({
                "ok": False,
                "error": "No se ha podido identificar el DNI/NIE de "
                         "ningún documento del lote -- no se crea la "
                         "ficha para no guardar datos de identidad sin "
                         "verificar. Si es un trabajador nuevo, incluye "
                         "al menos un documento que traiga su DNI (el "
                         "propio DNI/NIE, un contrato, un ALTA de la "
                         "Seguridad Social...). Si es para añadir o "
                         "actualizar documentación de alguien que ya "
                         "está dado de alta, hazlo desde su propia "
                         "ficha -- este botón es solo para altas "
                         "nuevas.",
            }, status=400)

        # H24 (S144), Miguel Ángel: si ya existe pero está de baja, el
        # alta lo reactiva, guarda su documentación y lleva su carpeta a
        # ACTIVOS (también en local). Solo un activo sigue bloqueado.
        if existing_person and not existing_person.is_active_employee:
            return JsonResponse({
                "ok": True,
                "duplicate": False,
                "draft": draft,
                "warnings": merged["warnings"],
                "per_file": per_file,
                "reactivate": {
                    "id": existing_person.pk,
                    "label": "%s %s, %s" % (
                        existing_person.first_surname,
                        existing_person.second_surname,
                        existing_person.given_name,
                    ),
                },
            })

        if existing_person:
            return JsonResponse({
                "ok": True,
                "duplicate": True,
                "draft": draft,
                "warnings": merged["warnings"],
                "per_file": per_file,
                "existing_person_id": existing_person.pk,
                "existing_person_label": "%s %s, %s" % (
                    existing_person.first_surname,
                    existing_person.second_surname,
                    existing_person.given_name,
                ),
            })

        return JsonResponse({
            "ok": True,
            "duplicate": False,
            "draft": draft,
            "warnings": merged["warnings"],
            "per_file": per_file,
        })


class PersonnelCreateView(DocsUploadAccessMixin, View):
    """
    H31 (S100), Bloque 1 -- PASO 2 (confirmación/creación) del alta
    guiada por documentación. Crea el `PersonIdentity` real que hasta
    ahora no existía -- confirmado contra el código real
    (`import_worker_machine_excel.py`, línea
    `person = PersonIdentity.objects.get(dni=dni)`) que la importación
    del Excel NUNCA crea filas nuevas, solo actualiza las que ya
    existen por DNI: el hueco de "cómo nace un PersonIdentity que
    todavía no está en el Excel" es exactamente el que cubre esta
    vista.

    CORREGIDO EN LA MISMA SESIÓN (S100): la primera versión de esta
    vista era un formulario manual puro -- Miguel Ángel corrigió que
    el alta real es guiada por documentación (ver anexo H31, sección
    "CORRECCIÓN CRÍTICA..."): el supervisor sube DNI/contrato,
    `PersonalIntakeExtractView` (paso 1) extrae los datos y precarga
    este formulario, y el supervisor solo confirma o corrige un campo
    puntual -- nunca teclea desde cero. Esta vista sigue aceptando los
    mismos campos de texto (siguen siendo necesarios como respaldo
    manual cuando la extracción falla del todo o el supervisor
    corrige), pero además recibe los MISMOS archivos ya extraídos en
    el paso 1 (campo `documents`, reenviados por el propio navegador)
    junto con el tipo documental ya detectado por archivo
    (`document_type_codes`, alineado por índice) para indexarlos de
    verdad en la carpeta de la persona recién creada -- sin repetir la
    llamada a Gemini, que ya se hizo en el paso 1.

    `is_active_employee=True` siempre -- esta vía de alta es,
    por definición, para personal activo (ver anexo H31, alcance
    "SOLO personal ACTIVO"). `folder_path` se calcula con la misma
    regla real ACTIVOS/{EMPRESA|GERENCIA|SIN_EMPRESA} que usa
    `restructure_personal_folders` (S99), compartida ahora vía
    `naming_service.build_person_category_root()` para no duplicarla
    (S100).
    """

    REQUIRED_FIELDS = ("dni", "first_surname", "given_name")
    OPTIONAL_TEXT_FIELDS = (
        "second_surname", "employer_company", "phone", "phone_secondary",
        "email", "address_street", "postal_code", "city", "province",
        "ss_affiliation_number", "professional_category",
    )
    OPTIONAL_DATE_FIELDS = ("birth_date", "hire_date")

    @staticmethod
    def _normalize_dni(raw_dni):
        return personal_intake_service.normalize_dni(raw_dni)

    # H31 (S100), ampliado tras petición de Miguel Ángel: "mejoramos
    # para incluir el resto de documentos. Supuestamente ya
    # disponemos de lo necesario para clasificar todo lo referente a
    # personal." Ya no hay una lista fija de 3 tipos -- se sube
    # cualquier documento cuyo `document_type_code` resuelva contra un
    # `DocumentTypeCatalog` real, activo, del dominio PERSONAL (ver
    # `_store_documents`, misma consulta que ya hace
    # `personal_intake_service` para construir el vocabulario de
    # extracción -- un tipo nuevo que se dé de alta en el catálogo se
    # permite solo, sin tocar este archivo). Solo `DESCONOCIDO` (o
    # cualquier código que no exista de verdad en el catálogo) se
    # sigue descartando sin subir -- el supervisor lo sube después por
    # la vía normal de la ficha ya creada.

    def _store_documents(self, request, person, folder_path):
        """
        H31 (S100). Sube de verdad a GCS e indexa (`DocumentIndexEntry`)
        cada archivo ya confirmado por el supervisor -- mismo mecanismo
        de subida (`spare_parts.gcs_service.upload_bytes`) y de
        nombrado (`naming_service.build_filename_personal`) que el
        resto de la plataforma, nunca inventado aquí. Un fallo al
        indexar un archivo concreto no revierte el alta ya confirmada
        del trabajador -- se informa como aviso, el supervisor puede
        subir ese documento después por la vía normal de la ficha.

        CORREGIDO EN LA MISMA SESIÓN (S100), incidente real con los 2
        DNI reales de Miguel Ángel: al principio solo se subían
        DNI/CONTRATO/RECONOCIMIENTO_MEDICO; ampliado después (mismo
        día, petición explícita) a TODO el catálogo real de PERSONAL
        -- cualquier `DESCONOCIDO` (código que no resuelve contra
        `DocumentTypeCatalog`, domain="PERSONAL", is_active=True) se
        sigue descartando sin subir, nunca entra a la ficha por esta
        vía. Además, cuando llegan varios documentos del mismo tipo
        con `tracks_expiry=True` (2 DNI, uno caducado y otro vigente),
        se aplica la sustitución real
        (`document_management.vigencia_service.evaluate_substitution`,
        mismo mecanismo ya usado por `subject_upload_service` para la
        subida desde ficha) -- el de fecha de caducidad más reciente
        queda vigente, el otro se marca `is_obsolete=True` y queda
        registrado en `DocumentSubstitutionLog`, en vez de dejar los
        dos "vigentes" a la vez sin ningún criterio, que es lo que
        pasó antes de esta corrección.
        """
        from document_explorer.models import DocumentIndexEntry
        from spare_parts.gcs_service import upload_bytes

        files = request.FILES.getlist("documents")
        type_codes = request.POST.getlist("document_type_codes")
        expiry_hints = request.POST.getlist("document_expiry_hints")
        issue_hints = request.POST.getlist("document_issue_hints")
        ct = ContentType.objects.get_for_model(PersonIdentity)
        today = timezone.now().date()
        warnings = []
        stored = 0
        skipped = []
        already = []
        # H31 (S100), incidente real reportado por Miguel Ángel: al
        # subir 2 DNI + 2 reconocimientos médicos en la misma alta,
        # `build_filename_personal` sin ordinal generaba el MISMO
        # nombre de archivo para los dos documentos del mismo tipo del
        # mismo día -- el segundo sobrescribía en GCS el blob del
        # primero en silencio, mientras se seguían creando filas
        # `DocumentIndexEntry` distintas apuntando a ese mismo blob ya
        # sobrescrito ("galimatías": 15 archivos subidos, varias
        # entradas duplicadas señalando al mismo objeto real).
        # Corregido: se cuenta cuántos nombres con el mismo prefijo
        # (persona+tipo+fecha) ya existen -- tanto ya indexados en BD
        # para esta persona (por si este mismo mecanismo se reutiliza
        # en el futuro para añadir documentos a alguien ya existente)
        # como los ya procesados en ESTE mismo lote -- y solo a partir
        # del segundo se añade el sufijo `_2`, `_3`... (`ordinal=None`
        # en el primero, igual que antes, para no cambiar el nombre en
        # el caso normal sin colisión).
        prefix_counts = {}
        # H31 (S100): snapshots "vigentes hasta ahora" de esta misma
        # sesión de alta, por código de tipo -- se van acumulando a
        # medida que se crean entries, para poder comparar cada
        # documento nuevo contra los ya creados en este mismo lote
        # (nunca hay preexistentes reales en un alta, pero el mismo
        # bucle sirve igual si en el futuro se reutiliza para añadir
        # documentos a una persona ya existente).
        current_by_type = {}
        company = Company.objects.first()

        for idx, f in enumerate(files):
            code = type_codes[idx] if idx < len(type_codes) else "DESCONOCIDO"
            document_type = DocumentTypeCatalog.objects.filter(
                code=code, domain="PERSONAL", is_active=True,
            ).first()
            if document_type is None:
                skipped.append(f.name)
                continue
            # H24 (S144), prueba con Cruces Gómez: el alta subía otra vez
            # documentos que ya estaban en el cubo. Mismo criterio que el
            # agente (S128): si el contenido ya está en el cubo, no se
            # sube ni se clasifica.
            content_md5 = base64.b64encode(
                hashlib.md5(f.read()).digest()).decode("ascii")
            f.seek(0)
            if DocumentIndexEntry.objects.filter(
                bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                md5_hash=content_md5, purged_at__isnull=True,
            ).exists():
                already.append(f.name)
                continue
            type_code_for_name = document_type.code
            extension = (
                f.name.rsplit(".", 1)[-1] if "." in f.name else "pdf"
            )
            base_prefix = naming_service.build_filename_personal(
                person.first_surname, person.second_surname,
                person.given_name, type_code_for_name,
                today, extension=extension,
            ).rsplit(".", 1)[0]
            if base_prefix not in prefix_counts:
                prefix_counts[base_prefix] = DocumentIndexEntry.objects.filter(
                    bucket=BUCKET, domain_content_type=ct,
                    domain_object_id=person.pk,
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    deleted_at__isnull=True, purged_at__isnull=True,
                    name__startswith=base_prefix,
                ).count()
            prefix_counts[base_prefix] += 1
            ordinal = (
                prefix_counts[base_prefix]
                if prefix_counts[base_prefix] > 1 else None
            )
            filename = naming_service.build_filename_personal(
                person.first_surname, person.second_surname,
                person.given_name, type_code_for_name,
                today, ordinal=ordinal, extension=extension,
            )
            blob_name = "%s/%s" % (folder_path, filename)
            data = f.read()

            # H31 (S100), incidente real: los hints de fecha (expiry_
            # hint/issue_hint) viajan desde la extracción hasta aquí
            # por tres capas (JSON -> JS -> formulario) -- el motor
            # real (`classify_dates_in_text`) demostró leer bien los
            # dos ALTA reales de Miguel Ángel en pruebas directas
            # contra el archivo, pero la ficha creada seguía guardando
            # `issue_date=None`; nunca se localizó en qué capa exacta
            # se perdía. En vez de seguir persiguiéndolo, se recalcula
            # aquí mismo, contra los bytes reales que se están
            # indexando -- para PDF, sobre su texto ya incrustado
            # (gratis, sin red) -- así el resultado nunca depende de
            # que el hint haya sobrevivido el viaje completo. Para
            # imágenes se sigue confiando en el hint ya extraído (aquí
            # no se repite Cloud Vision, sería una llamada de red
            # más).
            engine_expiry_date, engine_issue_date = None, None
            logger.warning(
                "# [DIAG-FECHAS] archivo=%s extension=%r len(data)=%d",
                f.name, extension, len(data),
            )
            if extension.lower() == "pdf":
                embedded_text = personal_intake_service._pdf_embedded_text(
                    data
                )
                logger.warning(
                    "# [DIAG-FECHAS] archivo=%s len(embedded_text)=%d "
                    "primeros_200=%r",
                    f.name, len(embedded_text), embedded_text[:200],
                )
                if embedded_text:
                    from document_explorer.date_verification_service import (
                        classify_dates_in_text,
                    )
                    engine_expiry_date, engine_issue_date, _others = (
                        classify_dates_in_text(embedded_text)
                    )
                    logger.warning(
                        "# [DIAG-FECHAS] archivo=%s expiry=%r issue=%r",
                        f.name, engine_expiry_date, engine_issue_date,
                    )

            expiry_date = (
                engine_expiry_date
                if document_type and document_type.tracks_expiry else None
            )
            if expiry_date is None:
                raw_expiry = (
                    expiry_hints[idx] if idx < len(expiry_hints) else ""
                )
                if (
                    document_type
                    and document_type.tracks_expiry
                    and raw_expiry
                ):
                    try:
                        year, month, day = (
                            int(x) for x in raw_expiry.split("-")
                        )
                        expiry_date = date(year, month, day)
                    except ValueError:
                        expiry_date = None

            # H31 (S100), verbatim Miguel Ángel: "tengo dos altas, una
            # con grúas Adolfo y otra con asistencia y grúa, y no es
            # capaz de decir cuál es la vigente" -- ALTA (y muchos
            # otros tipos del catálogo) no tienen fecha de caducidad
            # propia; `document_management.vigencia_service` ya sabe
            # resolver ese caso comparando por `issue_date` (el más
            # reciente gana). Sin exigir `tracks_expiry` aquí a
            # propósito -- el caso real es justo el de los tipos que
            # NO tienen caducidad.
            issue_date = engine_issue_date
            if issue_date is None:
                raw_issue = issue_hints[idx] if idx < len(issue_hints) else ""
                if raw_issue:
                    try:
                        year, month, day = (
                            int(x) for x in raw_issue.split("-")
                        )
                        issue_date = date(year, month, day)
                    except ValueError:
                        issue_date = None

            try:
                upload_bytes(
                    BUCKET, blob_name, data,
                    content_type=f.content_type or "application/octet-stream",
                )
                entry = DocumentIndexEntry.objects.create(
                    bucket=BUCKET,
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    blob_name=blob_name,
                    blob_name_hash=path_digest(blob_name),
                    parent_path=folder_path,
                    parent_path_hash=path_digest(folder_path),
                    name=filename,
                    size_bytes=len(data),
                    md5_hash=content_md5,
                    content_type=f.content_type or "application/octet-stream",
                    document_type=document_type,
                    domain_content_type=ct,
                    domain_object_id=person.pk,
                    expiry_date=expiry_date,
                    issue_date=issue_date,
                )
                stored += 1

                # H31 (S100): la sustitución ya NO se limita a
                # `tracks_expiry=True` -- `evaluate_substitution()`
                # sabe decidir igual de bien por `issue_date` cuando
                # no hay `expiry_date` (ver docstring de
                # `vigencia_service`), que es precisamente el caso de
                # ALTA y de la mayoría de tipos sin caducidad propia.
                # Limitarlo a `tracks_expiry` era justo lo que dejaba
                # dos ALTA "vigentes" a la vez sin ningún criterio.
                # H30 (S122): un tipo acumulable (varios vigentes a la
                # vez -- contratos, altas, cursos, entregas...) nunca
                # entra en la sustitución (vigencia_service deja este
                # filtro al llamador y aquí faltaba).
                if document_type is not None and document_type.is_cumulative:
                    continue
                existing_snapshots = current_by_type.get(code, [])
                incoming_snapshot = DocumentSnapshot(
                    identifier=entry.pk, expiry_date=entry.expiry_date,
                    issue_date=entry.issue_date, indexed_at=entry.indexed_at,
                )
                result = evaluate_substitution(
                    incoming_snapshot, existing_snapshots,
                )
                if result.incoming_should_prevail:
                    for old_id, _old_expiry in [
                        (s.identifier, s.expiry_date)
                        for s in existing_snapshots
                        if s.identifier in result.existing_to_archive
                    ]:
                        old_entry = DocumentIndexEntry.objects.get(pk=old_id)
                        old_entry.is_obsolete = True
                        old_entry.save(update_fields=["is_obsolete"])
                        if company:
                            DocumentSubstitutionLog.objects.create(
                                company=company,
                                superseding_content_type=(
                                    ContentType.objects.get_for_model(
                                        DocumentIndexEntry,
                                    )
                                ),
                                superseding_object_id=entry.pk,
                                superseding_label=entry.name,
                                superseded_content_type=(
                                    ContentType.objects.get_for_model(
                                        DocumentIndexEntry,
                                    )
                                ),
                                superseded_object_id=old_entry.pk,
                                superseded_label=old_entry.name,
                                subject_label=str(person),
                                document_type=code,
                                reasoning=result.reasoning,
                            )
                    current_by_type[code] = [
                        s for s in existing_snapshots
                        if s.identifier not in result.existing_to_archive
                    ] + [incoming_snapshot]
                else:
                    entry.is_obsolete = True
                    entry.save(update_fields=["is_obsolete"])
                    current_by_type[code] = existing_snapshots
            except Exception as exc:
                logger.warning(
                    "# [PersonalCreateView] Fallo indexando %s para "
                    "PersonIdentity %s: %s", f.name, person.pk, exc,
                    exc_info=True,
                )
                warnings.append(
                    "No se pudo indexar %s -- súbelo de nuevo desde la "
                    "ficha ya creada." % f.name,
                )

        if already:
            warnings.append(
                "Ya estaban en el cubo (no se suben otra vez): %s."
                % ", ".join(already),
            )
        if skipped:
            warnings.append(
                "%d documento(s) no reconocido(s) (%s) no se han subido -- "
                "súbelos desde la ficha ya creada una vez confirmada."
                % (len(skipped), ", ".join(skipped)),
            )
        return stored, warnings

    def _reactivate(self, request, person, data, date_values, section):
        """
        H24 (S144). Onboarding of a worker who already exists but is
        terminated: reactivate, store the new documents, local sync.

        ---

        Alta de un trabajador que ya existe pero está de baja (Miguel
        Ángel: "debería de reactivar ese trabajador y clasificar su
        documentación y descargarla a su local"). Toma la empresa del
        alta si viene, lo reactiva con la fecha de alta como
        recontratación (su documentación pasa a ACTIVOS/<EMPRESA>),
        guarda los documentos nuevos en su carpeta y crea la descarga
        a local, que además mueve su carpeta de INACTIVOS y la borra.
        """
        company_user = request.user.company_user
        previous_local = local_download_service.snapshot_paths(person)
        if data["employer_company"]:
            person.employer_company = data["employer_company"]
            person.save(update_fields=["employer_company", "updated_at"])
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        _reactivate_person(
            person, date_values["hire_date"], person_ct, company_user,
            local_sync=False,
        )
        person.refresh_from_db()
        # S146: su sección desde la fecha de alta, antes de mover su
        # carpeta local (la categoría local sale de la sección).
        from hr_calendar.balance import assign_section

        assign_section([person], section, date_values["hire_date"],
                       company_user)
        ensure_folder_chain(BUCKET, person.folder_path)
        stored_count, doc_warnings = self._store_documents(
            request, person, person.folder_path,
        )
        # S148: caducidades (DNI, permiso, reconocimiento) y C.P. a la
        # ficha desde los documentos del alta.
        if stored_count:
            from document_explorer.person_facts_service import (
                refresh_person,
            )

            refresh_person(person)
        download_job = local_download_service.create_for_person(
            person, company_user, previous_local,
        )
        return JsonResponse({
            "ok": True,
            "reactivated": True,
            "person_id": person.pk,
            "documents_stored": stored_count,
            "warnings": doc_warnings,
            "download": {
                "total": len(download_job.files),
                "status_url": reverse(
                    "new_ui:person_local_download",
                    kwargs={"pk": download_job.pk},
                ),
            } if download_job else None,
            "redirect_url": reverse("new_ui:home") + "?s=per",
        })

    def post(self, request):
        data = {
            field: request.POST.get(field, "").strip()
            for field in self.REQUIRED_FIELDS + self.OPTIONAL_TEXT_FIELDS
        }
        data["dni"] = self._normalize_dni(data["dni"])

        missing = [f for f in self.REQUIRED_FIELDS if not data[f]]
        if missing:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Faltan campos obligatorios: %s."
                    % ", ".join(missing),
                },
                status=400,
            )

        if data["employer_company"] not in dict(ALTA_COMPANY_CHOICES):
            return JsonResponse(
                {"ok": False, "error": "Elige la empresa."}, status=400,
            )
        raw_section = request.POST.get("section_id", "")
        section = Section.objects.filter(
            pk=raw_section if raw_section.isdigit() else 0,
            company=request.user.company_user.company,
        ).first()
        if section is None:
            return JsonResponse(
                {"ok": False, "error": "Elige la sección."}, status=400,
            )

        existing = PersonIdentity.objects.filter(dni=data["dni"]).first()
        reactivate = (
            existing is not None and not existing.is_active_employee
            and request.POST.get("reactivate_person_id") == str(existing.pk)
        )
        if existing is not None and not reactivate:
            # S148 (alta por formulario): si está de baja, se ofrece
            # reactivarla, igual que en el alta por documentos.
            offer = None if existing.is_active_employee else {
                "id": existing.pk,
                "label": "%s %s, %s" % (
                    existing.first_surname, existing.second_surname,
                    existing.given_name,
                ),
            }
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Ya existe una persona con el DNI/NIE %s."
                    % data["dni"],
                    "reactivate": offer,
                },
                status=400,
            )

        date_values = {}
        for field in self.OPTIONAL_DATE_FIELDS:
            raw_value = request.POST.get(field, "").strip()
            if not raw_value:
                date_values[field] = None
                continue
            try:
                year, month, day = (int(x) for x in raw_value.split("-"))
                date_values[field] = date(year, month, day)
            except ValueError:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Fecha con formato inválido en %s." % field,
                    },
                    status=400,
                )
        # H31 (S100): fecha de alta por defecto = hoy si el supervisor
        # no la escribe -- un alta de trabajador siempre tiene una
        # fecha real de entrada, nunca queda en blanco por omisión.
        if date_values["hire_date"] is None:
            date_values["hire_date"] = timezone.now().date()

        if reactivate:
            return self._reactivate(
                request, existing, data, date_values, section)

        # H31 (S100), Miguel Ángel: "lo que sí sabemos es la población
        # donde vive [...] debe de haber una tabla [...] donde
        # podamos descargarnos los códigos postales de las
        # poblaciones." Si el supervisor (o la extracción) no trae
        # C.P. pero sí población, se rellena solo contra el dataset
        # real del INE -- nunca inventado, nunca sobrescribe un C.P.
        # ya indicado a mano.
        postal_code = data["postal_code"]
        if not postal_code and data["city"]:
            # S148: primero el C.P. de la dirección (CartoCiudad); si no,
            # el del municipio (S100).
            postal_code = (
                postal_code_service.address_postal_code(
                    data["address_street"], data["city"])
                or postal_code_service.lookup_postal_code(data["city"])
            )

        folder_root = naming_service.build_person_category_root(
            data["first_surname"], data["second_surname"],
            data["employer_company"], True,
        )
        folder_name = naming_service.build_person_folder_name(
            data["first_surname"], data["second_surname"], data["given_name"],
        )
        folder_path = "%s/%s" % (folder_root, folder_name)

        person = PersonIdentity(
            # S125: sin este vínculo la ficha queda fuera de WhatsApp
            # (adjuntos, "Leer aquí", envíos), que resuelven por Company.
            company=request.user.company_user.company,
            dni=data["dni"],
            first_surname=data["first_surname"],
            second_surname=data["second_surname"],
            given_name=data["given_name"],
            is_active_employee=True,
            employer_company=data["employer_company"],
            phone=data["phone"],
            phone_secondary=data["phone_secondary"],
            email=data["email"],
            address_street=data["address_street"],
            postal_code=postal_code,
            city=data["city"],
            province=data["province"],
            ss_affiliation_number=data["ss_affiliation_number"],
            professional_category=data["professional_category"],
            birth_date=date_values["birth_date"],
            hire_date=date_values["hire_date"],
            folder_path=folder_path,
        )
        try:
            person.full_clean()
        except ValidationError as exc:
            return JsonResponse(
                {"ok": False, "error": "; ".join(exc.messages)}, status=400,
            )
        person.save()
        ensure_folder_chain(BUCKET, folder_path)
        # S146: su sección desde la fecha de alta; decide también su
        # carpeta local (TALLER, ADMINISTRACION... o OPERARIOS).
        from hr_calendar.balance import assign_section

        assign_section([person], section, date_values["hire_date"],
                       request.user.company_user)

        stored_count, doc_warnings = self._store_documents(
            request, person, folder_path,
        )
        # S148: caducidades (DNI, permiso, reconocimiento) y C.P. a la
        # ficha desde los documentos del alta (y C.P. por la dirección
        # aunque no haya documentos).
        from document_explorer.person_facts_service import refresh_person

        refresh_person(person)
        # H24 (S144): el alta termina cuando sus documentos están en la
        # carpeta local de OneDrive (los descarga el agente H28).
        # S148 (alta por formulario): sin documentos, el agente crea
        # igualmente su carpeta local vacía.
        from document_explorer.local_download_service import (
            create_for_person,
        )
        download_job = create_for_person(
            person, getattr(request.user, "company_user", None),
            always=True,
        )

        return JsonResponse(
            {
                "ok": True,
                "person_id": person.pk,
                "documents_stored": stored_count,
                "warnings": doc_warnings,
                "download": {
                    "total": len(download_job.files),
                    "status_url": reverse(
                        "new_ui:person_local_download",
                        kwargs={"pk": download_job.pk},
                    ),
                } if download_job else None,
                "redirect_url": reverse("new_ui:home") + "?s=per",
            }
        )


class PersonnelTerminateView(DocsUploadAccessMixin, View):
    """
    H31 (S117). POST: baja por RESCISIÓN DE CONTRATO (el trabajador
    deja la empresa) de uno o varios trabajadores a la vez -- nunca
    confundir con una baja médica/ITL (hr_calendar.MedicalLeavePeriod).
    Mismo proceso que "Dar de baja" en Centros de gasto, decisión
    explícita de Miguel Ángel: "señalo en el listado, en el casillero
    50 personas y en el panel de acciones me aparece ya accionable el
    botón de dar de baja [...] con fecha del día [...] la selección de
    personal la haces desde el CRUD, no desde el modal" -- el modal del
    frontend solo confirma.

    Aplica lo ya decidido en S100 para la baja: pasa a inactivo, se
    guarda la fecha de baja (HOY) y su documentación va a la carpeta de
    inactivos, desde donde se consulta en el explorador de archivos.
    Reutiliza sin duplicar la regla de carpetas de S99
    (naming_service.build_person_category_root -> PERSONAL/INACTIVOS) y
    el movimiento VIRTUAL de move_service.move_entries() por
    domain_object real (4.12: nunca se toca GCS), igual que
    restructure_personal_folders. Una transacción por persona: si una
    falla, las demás no se deshacen.

    POST person_ids (uno o varios).
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        if not person_ids:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "No hay ningún trabajador seleccionado.",
                },
                status=400,
            )
        today = timezone.localdate()
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        terminated_ids = []
        skipped_names = []
        moved_total = 0
        for person in PersonIdentity.objects.filter(pk__in=person_ids):
            if not person.is_active_employee:
                skipped_names.append(_person_display_name(person))
                continue
            moved_total += _terminate_person(
                person, today, person_ct, request.user.company_user,
            )
            terminated_ids.append(person.pk)
        return JsonResponse({
            "ok": True,
            "terminated_count": len(terminated_ids),
            "terminated_ids": terminated_ids,
            "skipped_names": skipped_names,
            "moved_count": moved_total,
        })


def _person_display_name(person):
    """
    "APELLIDO1 APELLIDO2, NOMBRE", same format as the list.
    ---
    "APELLIDO1 APELLIDO2, NOMBRE", mismo formato que el listado.
    """
    return "%s %s, %s" % (
        person.first_surname, person.second_surname, person.given_name,
    )


def _terminate_person(person, termination_date, person_ct, company_user):
    """
    H31 (S117). Marks one worker as terminated (rescisión de contrato)
    and moves his/her documentation virtually to PERSONAL/INACTIVOS.
    Returns the number of documents moved.
    ---
    Marca un trabajador como dado de baja (rescisión de contrato) y
    mueve virtualmente su documentación a PERSONAL/INACTIVOS. Devuelve
    el número de documentos movidos.
    """
    from django.db import transaction

    from document_explorer.person_folder_service import (
        expected_base_folder, free_folder_for, move_person_documents,
    )

    # Mismo criterio que restructure_personal_folders ante homónimos:
    # nunca mezclar la documentación de dos personas en una carpeta --
    # sufijo _2, _3... si ya tiene documentos de OTRA persona (S125:
    # compartido en person_folder_service).
    new_folder_path = free_folder_for(
        person, expected_base_folder(person, is_active=False),
    )
    previous_local = local_download_service.snapshot_paths(person)

    with transaction.atomic():
        moved = move_person_documents(person, new_folder_path)
        person.is_active_employee = False
        person.termination_date = termination_date
        person.save(update_fields=[
            "is_active_employee", "termination_date", "updated_at",
        ])
        # S117 -- Miguel Ángel: "hay que desactivar su cuenta de acceso
        # si la tiene". Se desactiva en los dos sitios que la gobiernan:
        # CompanyUser.is_active (acceso al panel) y User.is_active de
        # Django (bloquea el inicio de sesión).
        account_disabled = _set_person_account_active(person, False)
    # H24 (S144): "poner inactivo a una persona en el panel y que [...]
    # en el local también la ponga en inactivos" (agente H28).
    local_download_service.create_for_person(
        person, company_user, previous_local,
    )
    logger.info(
        "# [H31-BAJA] PersonIdentity pk=%s dado de baja (rescisión) con "
        "fecha %s por CU pk=%s -- %d documento(s) movidos a %s; cuenta "
        "de acceso desactivada: %s.",
        person.pk, termination_date, company_user.pk, moved,
        new_folder_path, account_disabled,
    )
    return moved


def _set_person_account_active(person, active):
    """
    S117. Enables/disables the panel account linked to a worker
    (PersonIdentity.company_user), if any: CompanyUser.is_active and the
    Django User.is_active. Never touches a pending pre-registration
    (pending_onboarding), which is not a usable account yet. Returns
    True if an account was changed.
    ---
    Activa/desactiva la cuenta del panel enlazada a un trabajador
    (PersonIdentity.company_user), si la tiene: CompanyUser.is_active y
    User.is_active de Django. Nunca toca un pre-registro pendiente
    (pending_onboarding), que aún no es una cuenta utilizable. Devuelve
    True si se ha cambiado alguna cuenta.
    """
    account = person.company_user
    if account is None or account.pending_onboarding:
        return False
    account.is_active = active
    account.save(update_fields=["is_active"])
    if account.user_id:
        account.user.is_active = active
        account.user.save(update_fields=["is_active"])
    return True


def _reactivate_person(person, rehire_date, person_ct, company_user,
                       local_sync=True):
    """
    S117. Undoes a termination or re-hires a worker: back to active,
    termination date cleared, documentation moved back (virtually) to
    his/her ACTIVOS folder (same S99 rule), panel account re-enabled.
    With rehire_date, the hire date becomes that date (re-hiring);
    without it, the original hire date is kept (undo). Returns the
    number of documents moved.
    ---
    Deshace una baja o recontrata a un trabajador: vuelve a activo, se
    borra la fecha de baja, su documentación vuelve (virtualmente) a su
    carpeta de ACTIVOS (misma regla de S99) y se reactiva su cuenta del
    panel. Con rehire_date, la fecha de alta pasa a ser esa
    (recontratación); sin ella, se conserva la fecha de alta original
    (deshacer). Devuelve el número de documentos movidos.
    """
    from django.db import transaction

    from document_explorer.person_folder_service import (
        expected_base_folder, free_folder_for, move_person_documents,
    )

    new_folder_path = free_folder_for(
        person, expected_base_folder(person, is_active=True),
    )
    previous_local = local_download_service.snapshot_paths(person)

    with transaction.atomic():
        moved = move_person_documents(person, new_folder_path)
        person.is_active_employee = True
        person.termination_date = None
        update_fields = [
            "is_active_employee", "termination_date", "updated_at",
        ]
        if rehire_date:
            person.hire_date = rehire_date
            update_fields.append("hire_date")
        person.save(update_fields=update_fields)
        account_enabled = _set_person_account_active(person, True)
    # H24 (S144): su carpeta local vuelve también a ACTIVOS (agente H28).
    # El alta de un trabajador de baja lo pide ella misma, después de
    # guardar los documentos nuevos (`local_sync=False`).
    if local_sync:
        local_download_service.create_for_person(
            person, company_user, previous_local,
        )
    logger.info(
        "# [H31-REACTIVAR] PersonIdentity pk=%s reactivado (%s) por CU "
        "pk=%s -- %d documento(s) movidos a %s; cuenta reactivada: %s.",
        person.pk,
        "recontratación %s" % rehire_date if rehire_date else "deshacer baja",
        company_user.pk, moved, new_folder_path, account_enabled,
    )
    return moved


class PersonnelReactivateView(DocsUploadAccessMixin, View):
    """
    H31 (S117). POST: deshace la baja por rescisión de contrato o
    recontrata a uno o varios trabajadores inactivos -- Miguel Ángel:
    "evidentemente es preciso poder recontratar o deshacer". Mismo
    patrón que PersonalTerminateView: la selección se hace en el
    listado y el modal solo confirma. Con rehire=1, la fecha de alta
    pasa a ser HOY (recontratación); sin él, se conserva la original
    (deshacer una baja dada por error).

    POST person_ids (uno o varios), rehire ("1" o vacío).
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        if not person_ids:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "No hay ningún trabajador seleccionado.",
                },
                status=400,
            )
        rehire_date = (
            timezone.localdate() if request.POST.get("rehire") == "1" else None
        )
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        reactivated_ids = []
        skipped_names = []
        moved_total = 0
        for person in PersonIdentity.objects.filter(pk__in=person_ids):
            if person.is_active_employee:
                skipped_names.append(_person_display_name(person))
                continue
            moved_total += _reactivate_person(
                person, rehire_date, person_ct, request.user.company_user,
            )
            reactivated_ids.append(person.pk)
        return JsonResponse({
            "ok": True,
            "reactivated_count": len(reactivated_ids),
            "reactivated_ids": reactivated_ids,
            "skipped_names": skipped_names,
            "moved_count": moved_total,
            "rehire": bool(rehire_date),
        })


class PersonLocalDownloadStatusView(DocsUploadAccessMixin, View):
    """
    JSON state of one local download.

    ---

    Estado (JSON) de una descarga a la carpeta local (copia de
    panel/views_personal_local_download.py).
    """

    def get(self, request, pk):
        from document_explorer.local_download_service import status_payload
        from document_explorer.models import LocalDownloadJob

        job = get_object_or_404(LocalDownloadJob, pk=pk)
        return JsonResponse(status_payload(job))


# ------------------------------------------------- avisos para Acciones
def _payload(response):
    import json

    try:
        return json.loads(response.content or b"{}")
    except ValueError:
        return None


def _respond(data, status, message):
    data["message"] = message
    return JsonResponse(data, status=status)


class NuiIntakeExtractView(PersonnelIntakeExtractView):
    """Lectura del alta, con el aviso de Acciones."""

    def post(self, request):
        response = super().post(request)
        data = _payload(response)
        if data is None:
            return response
        if not data.get("ok"):
            return _respond(data, response.status_code,
                            data.get("error") or "No se han podido leer.")
        if data.get("duplicate"):
            message = ("Ya está dado de alta: %s. Su documentación se sube "
                       "desde su ficha." % data["existing_person_label"])
        elif data.get("reactivate"):
            message = ("Está de baja: %s. Al confirmar, el alta lo "
                       "reactiva." % data["reactivate"]["label"])
        else:
            message = "Datos leídos: revísalos y confirma el alta."
        return _respond(data, response.status_code, message)


class NuiCreateView(PersonnelCreateView):
    """Alta, con el aviso de Acciones."""

    def post(self, request):
        response = super().post(request)
        data = _payload(response)
        if data is None:
            return response
        if not data.get("ok"):
            return _respond(data, response.status_code,
                            data.get("error") or "No se ha podido dar de "
                            "alta.")
        person = PersonIdentity.objects.filter(
            pk=data.get("person_id")).first()
        name = "%s %s, %s" % (person.first_surname, person.second_surname,
                              person.given_name) if person else ""
        data["person_label"] = name
        if person:
            # La vista se queda con la persona recién dada de alta.
            data["scope"] = {"pk": person.pk, "label": name}
        parts = ["%s: %s; %d documento(s) guardados." % (
            "Reactivado" if data.get("reactivated") else "Alta hecha",
            name, data.get("documents_stored", 0))]
        if data.get("download"):
            parts.append("Descarga a su carpeta local: %d archivo(s)." %
                         data["download"]["total"])
        parts.extend(data.get("warnings") or [])
        return _respond(data, response.status_code, " ".join(parts))


def _selected_as_person_ids(request):
    request.POST = request.POST.copy()
    request.POST.setlist("person_ids", request.POST.getlist("selected"))


class NuiTerminateView(PersonnelTerminateView):
    """Baja de los marcados, con el aviso de Acciones."""

    def post(self, request):
        _selected_as_person_ids(request)
        response = super().post(request)
        data = _payload(response)
        if not data.get("ok"):
            return _respond(data, response.status_code,
                            data.get("error") or "Error.")
        message = "Dados de baja: %d (documentación movida: %d)." % (
            data["terminated_count"], data["moved_count"])
        if data["skipped_names"]:
            message += " Ya estaban de baja: %s." % ", ".join(
                data["skipped_names"])
        return _respond(data, response.status_code, message)


class NuiReactivateView(PersonnelReactivateView):
    """Reactivar los marcados, con el aviso de Acciones."""

    def post(self, request):
        _selected_as_person_ids(request)
        response = super().post(request)
        data = _payload(response)
        if not data.get("ok"):
            return _respond(data, response.status_code,
                            data.get("error") or "Error.")
        message = "%s: %d (documentación movida: %d)." % (
            "Recontratados con fecha de hoy" if data["rehire"]
            else "Baja deshecha", data["reactivated_count"],
            data["moved_count"])
        if data["skipped_names"]:
            message += " Ya estaban activos: %s." % ", ".join(
                data["skipped_names"])
        return _respond(data, response.status_code, message)


def personnel_context(section):
    """Empresas y secciones del formulario de alta (solo Personal)."""
    if section != "per":
        return {}
    return {"alta_companies": ALTA_COMPANY_CHOICES}
