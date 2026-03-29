# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V01/V01DOC_CONNECTIVITY_TUNNEL_SPEC.md

# ESPECIFICACIÓN TÉCNICA: INFRAESTRUCTURA DE CONECTIVIDAD Y TÚNELES (NGROK V3)
# PROYECTO: EnterpriseBot
# FECHA: Marzo 2026
# ESTADO: LEY TÉCNICA PARA EL HITO 1

---

## 1. INTRODUCCIÓN Y PROPÓSITO / INTRODUCTION AND PURPOSE
Este documento define los estándares obligatorios para la capa de transporte y conectividad externa del proyecto EnterpriseBot. Debido a la arquitectura "Sidecar" necesaria para operar WebSockets en PythonAnywhere (entorno WSGI), se requiere un túnel seguro que exponga el puerto 8080 hacia la red pública para recibir la señalización binaria de Twilio Media Streams. Esta especificación técnica garantiza que la configuración sea persistente, auditable y compatible con los estándares de seguridad y protocolos de red vigentes en marzo de 2026.

## 2. ESTÁNDAR DE AGENTE: NGROK V3 / AGENT STANDARD: NGROK V3
A partir de las actualizaciones de infraestructura de 2026, el uso del agente ngrok v3 es MANDATORIO y EXCLUSIVO. Las versiones anteriores (v2.x) han sido completamente deprecadas y su uso en este proyecto se considera un Error Crítico debido a:
*   Incompatibilidad con los nuevos protocolos de negociación TLS 1.3.
*   Falta de soporte para la arquitectura de "Traffic Policies" dinámicas.
*   Vulnerabilidades reportadas en la gestión de WebSockets de larga duración (long-lived connections).

### 2.1. Ruptura de Compatibilidad (Breaking Changes)
*   **Esquema de Configuración:** El agente v3 ha eliminado el soporte para el campo raíz `tunnels:`. Toda definición de túnel o exposición de puerto debe realizarse bajo el bloque semántico `endpoints:`.
*   **Jerarquía del Agente:** Las credenciales de autenticación (`authtoken`) y las opciones globales de comportamiento del binario deben estar obligatoriamente anidadas bajo la clave `agent:`. Definirlas en el nivel superior del archivo YAML provocará un fallo de validación inmediata por parte del parser del agente.

## 3. ARQUITECTURA DE ENDPOINTS / ENDPOINTS ARCHITECTURE
En la versión 3 de ngrok, la abstracción ha evolucionado de un simple "túnel" a un "objeto endpoint" gestionado por políticas. Esto permite una granularidad mucho mayor en la inspección y filtrado del tráfico entrante.

### 3.1. Especificación del Endpoint 'enterprise_voice_bridge'
Este endpoint es el punto de entrada crítico para el flujo de audio de Twilio.
*   **Protocolo de Origen:** HTTP (con capacidad de upgrade automático a Secure WebSocket - WSS).
*   **Dirección Local (Upstream):** 127.0.0.1:8080. El sidecar de voz debe estar escuchando en este puerto exacto.
*   **Esquema de Red:** Uso obligatorio de HTTPS. Twilio Media Streams rechaza por diseño cualquier conexión que no viaje sobre un túnel cifrado.
*   **Inspección de Tráfico (Deep Packet Inspection):** Activada mediante la directiva `inspect: true`. Esta configuración es vital para el desarrollo, ya que permite al desarrollador auditar los paquetes JSON de señalización de Twilio (eventos start, media, stop) directamente desde el panel administrativo de ngrok en caso de fallos en el bridge.

## 4. ESPECIFICACIÓN DEL ARCHIVO DE CONFIGURACIÓN (YAML V3)
El archivo `ngrok.yml` en la raíz del proyecto debe adherirse de forma estricta al siguiente esquema para garantizar la interoperabilidad con el agente v3:

```yaml
version: "3"
agent:
  authtoken: ${NGROK_AUTHTOKEN} # Se recomienda inyección dinámica para evitar fugas de seguridad
  region: eu # Región de Europa obligatoria para minimizar la latencia de ida y vuelta (RTT)
  log: stdout
  log_level: info

endpoints:
  enterprise_voice_bridge:
    proto: http
    upstream:
      url: 8080
    traffic_policy:
      on_tcp_connection:
        - allow:
            name: "Permitir Tráfico Validado de Twilio"
            # Configuración de políticas de tráfico para filtrar por IPs de Twilio si es necesario
```

## 5. PROTOCOLO DE EJECUCIÓN EN PYTHONANYWHERE
PythonAnywhere impone restricciones sobre la ejecución de procesos persistentes. Para mitigar cierres inesperados del túnel, se establecen las siguientes normas de ejecución:

### 5.1. Gestión de Logs y Persistencia de Proceso
*   **Modo No Interactivo:** El túnel debe ejecutarse en segundo plano pero con redirección de salida absoluta.
*   **Unbuffered Log:** Se debe evitar el almacenamiento en buffer de la salida estándar para que los logs de conexión sean visibles en tiempo real en el archivo de auditoría de la sesión.
*   **Comando de Lanzamiento Estándar:**
    `./ngrok start --config ngrok.yml enterprise_voice_bridge >> /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/ngrok_runtime.log 2>&1 &`

## 6. SEGURIDAD Y GESTIÓN DE CREDENCIALES
*   Queda terminantemente prohibido escribir el `authtoken` en texto plano dentro de este documento o en cualquier archivo subido a repositorios de código.
*   La credencial debe residir exclusivamente en el entorno seguro del servidor (archivo `.env`).
*   El script de gestión del túnel debe realizar una verificación de existencia del token antes de intentar la conexión.

## 7. TRAZABILIDAD Y AUDITORÍA
Cualquier modificación en la infraestructura de red, cambio de puertos o actualización del binario de ngrok debe ser precedida por una actualización de este documento satélite. La desincronización entre esta especificación y la implementación física se considera un Error Crítico de Mantenibilidad.
