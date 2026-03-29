# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/models.py
from django.db import models

class CallInteraction(models.Model):
    """
    Model that represents a real-time voice interaction via Twilio Media Streams.
    ---
    Modelo que representa una interacción de voz en tiempo real a través de Twilio Media Streams.
    """
    
    # Twilio Identifiers / Identificadores de Twilio
    call_sid = models.CharField(max_length=100, unique=True, default='', verbose_name='SID de Llamada')
    stream_sid = models.CharField(max_length=100, null=True, blank=True, verbose_name='SID de Stream')
    account_sid = models.CharField(max_length=100, null=True, blank=True, verbose_name='SID de Cuenta')
    
    # Network Data / Datos de Red
    from_number = models.CharField(max_length=20, verbose_name='Número de Origen')
    to_number = models.CharField(max_length=20, verbose_name='Número de Destino')
    direction = models.CharField(max_length=20, default='inbound', verbose_name='Dirección')
    
    # Lifecycle and AI / Ciclo de Vida e IA
    STATUS_CHOICES = [
        ('queued', 'En cola'),
        ('ringing', 'Llamando'),
        ('in-progress', 'En curso (Streaming)'),
        ('completed', 'Completada'),
        ('failed', 'Fallida'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued', verbose_name='Estado de Interacción')
    
    full_transcript = models.TextField(null=True, blank=True, verbose_name='Historial de Conversación (Log)')
    department_detected = models.CharField(max_length=50, null=True, blank=True, verbose_name='Departamento Detectado')
    
    # Metrics and Audit / Métricas y Auditoría
    duration = models.IntegerField(null=True, blank=True, verbose_name='Duración')
    price = models.DecimalField(max_digits=10, decimal_places=5, null=True, blank=True, verbose_name='Coste Estimado')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Inicio')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')

    class Meta:
        verbose_name = 'Interacción de Voz Twilio'
        verbose_name_plural = 'Interacciones de Voz Twilio'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.call_sid} | {self.from_number} -> {self.status}'
