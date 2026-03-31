from django.db import models

# Create your models here.

class LiveTestLog(models.Model):
    """
    Model for auditing and diagnosing the Gemini 3.1 Live (v1beta) handshake and latencies.
    ---
    Modelo para la auditoría y diagnóstico del apretón de manos (handshake) y latencias de Gemini 3.1 Live (v1beta).
    """
    session_id = models.CharField(max_length=100, verbose_name="ID de Sesión")
    api_version = models.CharField(max_length=20, default="v1beta", verbose_name="Versión de API")
    model_name = models.CharField(max_length=100, default="models/gemini-3.1-flash-live-preview", verbose_name="Modelo")
    request_initiated_at = models.DateTimeField(auto_now_add=True, verbose_name="Inicio de Petición")
    setup_completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Handshake Completado")
    first_response_at = models.DateTimeField(null=True, blank=True, verbose_name="Primera Respuesta de IA")
    connection_closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Cierre de Conexión")
    handshake_latency_ms = models.IntegerField(null=True, blank=True, verbose_name="Latencia Handshake (ms)")
    is_successful = models.BooleanField(default=False, verbose_name="¿Éxito?")
    error_log = models.TextField(null=True, blank=True, verbose_name="Log de Errores")

    class Meta:
        verbose_name = "Log de Diagnóstico Live"
        verbose_name_plural = "Logs de Diagnóstico Live"
        ordering = ['-request_initiated_at']

    def __str__(self):
        return f"Test {self.session_id} - {'OK' if self.is_successful else 'FAIL'}"
