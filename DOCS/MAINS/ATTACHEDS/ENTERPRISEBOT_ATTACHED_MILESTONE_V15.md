# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V15.md

# ENTERPRISEBOT — ANEXO HITO 15
## Gestor de Árbol de Directorios con Power Automate

---

## Estado de Pasos

| Paso | Descripción | Estado |
|------|-------------|--------|
| 1 | Evaluación online de Power Automate — capacidades y conectores disponibles | PENDIENTE |
| 2 | Diseño de la interfaz de árbol de directorios destino | PENDIENTE |
| 3 | Implementación del lector de carpeta origen (OneDrive/SharePoint) | PENDIENTE |
| 4 | Motor de organización: mapeo de archivos según árbol definido | PENDIENTE |
| 5 | Integración con Power Automate o agente Django + IA (según evaluación Paso 1) | PENDIENTE |
| 6 | Validación E2E con carpeta real de la empresa | PENDIENTE |

---

## Contexto y Decisión Arquitectónica

### Descripción del problema

El usuario necesita una herramienta que:
1. Lea una carpeta origen (y sus subcarpetas y archivos) — ubicada en OneDrive o SharePoint.
2. Permita definir visualmente un árbol de directorios destino.
3. Organice automáticamente los archivos leídos según el árbol definido.

### Evaluación de Power Automate (Paso 1 — OBLIGATORIO)

La empresa ya dispone de licencia de Power Automate. Antes de construir
ningún agente propio, el Paso 1 debe evaluar online:

- Conectores disponibles: SharePoint, OneDrive for Business, File System.
- Acciones de listado recursivo de carpetas y archivos.
- Acciones de movimiento/copia de archivos entre rutas.
- Limitaciones de triggers y bucles (límite de iteraciones en flujos estándar).
- Si los conectores cubren el caso de uso sin código adicional:
  → implementar como flujo Power Automate puro (sin agente Django).
- Si los conectores son insuficientes o la lógica de mapeo es demasiado compleja:
  → construir agente Django + IA con llamadas a Microsoft Graph API.

**Directriz 4.4 — OBLIGATORIO:** actualizarse online antes de implementar
cualquier integración con Power Automate o Microsoft Graph API.

### Arquitectura tentativa (a confirmar tras Paso 1)

**Opción A — Power Automate puro:**
- Trigger manual o programado desde Power Automate.
- Conector SharePoint/OneDrive: listar archivos de la carpeta origen.
- Variable de configuración: árbol de directorios destino (JSON o tabla).
- Bucle de clasificación: para cada archivo, determinar carpeta destino
  según nombre, extensión o metadatos.
- Acción de movimiento/copia al destino.

**Opción B — Agente Django + Microsoft Graph API:**
- Interfaz web en el panel de EnterpriseBot donde el usuario construye
  el árbol de directorios destino (componente interactivo drag & drop o
  formulario jerárquico).
- Backend Django llama a Microsoft Graph API para listar la carpeta origen.
- Motor de clasificación IA (Gemini) asigna cada archivo a una carpeta
  del árbol según nombre, extensión y contenido si procede.
- Llamada a Graph API para mover/copiar cada archivo al destino.
- Autenticación: OAuth2 con cuenta Microsoft de la empresa.

---

## Hoja de Ruta para la Siguiente Sesión (S011)

### Bloque A — Evaluación y Decisión Arquitectónica

#### A1. Actualización online de Power Automate

Antes de cualquier implementación, el modelo debe buscar y leer:
- Documentación oficial de conectores Power Automate para SharePoint y OneDrive.
- Límites de iteraciones en flujos estándar y premium.
- Disponibilidad de acciones de listado recursivo de subcarpetas.
- Ejemplos de flujos de organización de archivos existentes.
- Comparativa de coste/complejidad entre Opción A y Opción B.

#### A2. Decisión y diseño

Tras la evaluación, presentar a Miguel Ángel:
- La opción recomendada con justificación técnica.
- El diseño detallado de la solución elegida.
- Los pasos de implementación concretos.

#### A3. Implementación

Según la decisión de A2, implementar la solución elegida comenzando por
la interfaz de usuario del árbol de directorios y el motor de lectura
de la carpeta origen.
