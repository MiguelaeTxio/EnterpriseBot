# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/models.py
from django.db import models

class CallInteraction(models.Model):
    """
    Model that represents a voice interaction received through the MundoSMS bridge.
    ---
    Modelo que representa una interacción de voz recibida a través del puente de MundoSMS.
    """
    
    # Identificadores de red / Network Identifiers
    call_id = models.CharField(
        max_length=100, 
        unique=True, 
        verbose_name="ID de Llamada"
    )
    phone_number = models.CharField(
        max_length=20, 
        verbose_name="Número de Teléfono"
    )
    
    # Datos de audio y procesamiento / Audio and Processing Data
    recording_url = models.URLField(
        max_length=500, 
        null=True, 
        blank=True, 
        verbose_name="URL de la Grabación"
    )
    transcription = models.TextField(
        null=True, 
        blank=True, 
        verbose_name="Transcripción de IA"
    )
    department_detected = models.CharField(
        max_length=50, 
        null=True, 
        blank=True, 
        verbose_name="Departamento Detectado"
    )
    
    # Metadatos / Metadata
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Fecha de Creación"
    )

    class Meta:
        verbose_name = "Interacción de Llamada"
        verbose_name_plural = "Interacciones de Llamadas"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phone_number} - {self.department_detected or 'Pendiente'}"
