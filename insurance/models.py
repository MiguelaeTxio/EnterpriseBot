# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/models.py
"""
Insurance renewal reports: uploaded 625 ledgers, the cached reading of
each insurance document and the reports built from both.

---

Informes de renovación de seguros (pestaña "Seguros" de Documentación,
encargo de Miguel Ángel en S152 para Yolanda y Alejandro): los libros
mayores de la cuenta 625 subidos, la lectura con Gemini de cada documento
de seguro del cubo (guardada para no volver a leer lo mismo en cada
informe) y los informes que se hacen con todo ello.
"""
from django.db import models


class InsuranceLedger(models.Model):
    """
    One uploaded "Listado Mayor Analítico" PDF of account 625.
    ---
    Un PDF del «Listado Mayor Analítico» de la cuenta 625 subido en la
    pestaña. Se lee al subirlo y se guarda el PDF en el cubo; los
    apuntes quedan aquí para cotejarlos en cualquier informe.
    """

    company_code = models.CharField(
        max_length=8, blank=True, verbose_name="Empresa",
        help_text="Código de insurance.companies; se detecta de la "
                  "cabecera del PDF y se puede cambiar.")
    original_name = models.CharField(max_length=255,
                                     verbose_name="Archivo")
    sha256 = models.CharField(max_length=64, db_index=True,
                              verbose_name="Huella del PDF")
    bucket = models.CharField(max_length=63, blank=True)
    blob_name = models.TextField(blank=True)
    date_from = models.DateField(null=True, blank=True,
                                 verbose_name="Periodo desde")
    date_to = models.DateField(null=True, blank=True,
                               verbose_name="Periodo hasta")
    printed_at = models.DateField(null=True, blank=True,
                                  verbose_name="Impreso el")
    entries = models.JSONField(default=list, blank=True,
                               verbose_name="Apuntes")
    entry_count = models.PositiveIntegerField(default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    uploaded_by = models.ForeignKey(
        "ivr_config.CompanyUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_to", "company_code", "-uploaded_at"]
        verbose_name = "Libro mayor de seguros"
        verbose_name_plural = "Libros mayores de seguros"

    def __str__(self):
        return "%s %s–%s" % (self.company_code, self.date_from,
                             self.date_to)


class InsuranceDocumentReading(models.Model):
    """
    Gemini's reading of one insurance document of the bucket (cache).
    ---
    Lectura con Gemini de un documento de seguro del cubo. Se repite
    solo si el archivo cambia (md5) o la lectura falló.
    """

    entry = models.OneToOneField(
        "document_explorer.DocumentIndexEntry", on_delete=models.CASCADE,
        related_name="insurance_reading")
    md5_hash = models.CharField(max_length=64, blank=True)
    data = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    read_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lectura de documento de seguro"
        verbose_name_plural = "Lecturas de documentos de seguro"


class InsuranceReport(models.Model):
    """
    A renewal report for a due-month range.
    ---
    Un informe de renovación: los seguros que vencen desde el mes
    elegido (y hasta el otro, si se pone), con los libros mayores
    marcados. Se hace en segundo plano; el resultado (seguros, avisos,
    cotejo con el mayor) queda en `data` para verlo y exportarlo.
    """

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "En cola"
        READING = "READING", "Leyendo documentos"
        BUILDING = "BUILDING", "Montando el informe"
        DONE = "DONE", "Terminado"
        ERROR = "ERROR", "Con error"

    title = models.CharField(max_length=200, blank=True,
                             verbose_name="Título")
    month_from = models.DateField(verbose_name="Vencimiento desde")
    month_to = models.DateField(null=True, blank=True,
                                verbose_name="Vencimiento hasta")
    companies = models.JSONField(
        default=list, blank=True, verbose_name="Empresas",
        help_text="Códigos de insurance.companies; vacío = todas.")
    ledgers = models.ManyToManyField(InsuranceLedger, blank=True,
                                     related_name="reports",
                                     verbose_name="Libros mayores")
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.QUEUED,
                              verbose_name="Estado")
    progress_done = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    progress_text = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    log = models.TextField(blank=True)
    data = models.JSONField(null=True, blank=True)
    policy_count = models.PositiveIntegerField(default=0,
                                               verbose_name="Seguros")
    premium_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Prima anual")
    alert_count = models.PositiveIntegerField(default=0,
                                              verbose_name="Avisos")
    created_by = models.ForeignKey(
        "ivr_config.CompanyUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Supervisor")
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Fecha del informe")
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Informe de seguros"
        verbose_name_plural = "Informes de seguros"

    def __str__(self):
        return self.title or "Informe de seguros #%s" % self.pk

    @property
    def is_live(self):
        return self.status in (self.Status.QUEUED, self.Status.READING,
                               self.Status.BUILDING)


class InsuranceReportExport(models.Model):
    """
    Each export of a report (format, who, when).
    ---
    Cada exportación de un informe (formato, quién y cuándo), para la
    columna «Exportado a» del listado.
    """

    class Format(models.TextChoices):
        HTML = "html", "HTML"
        XLSX = "xlsx", "Excel"
        PDF = "pdf", "PDF"
        DOCX = "docx", "Word"

    report = models.ForeignKey(InsuranceReport, on_delete=models.CASCADE,
                               related_name="exports")
    fmt = models.CharField(max_length=4, choices=Format.choices)
    exported_by = models.ForeignKey(
        "ivr_config.CompanyUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")
    exported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-exported_at"]
