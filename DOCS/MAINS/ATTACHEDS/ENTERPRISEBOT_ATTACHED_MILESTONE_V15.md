# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V15.md

# ENTERPRISEBOT -- ANEXO HITO 15
## Gestor de Archivos con Gemini Vision

---

## Estado de Pasos

| Paso | Descripcion | Estado |
|------|-------------|--------|
| 1 | Prueba de campo -- analisis de carpeta OBSOLETOS y generacion de informe de organizacion | PENDIENTE |
| 2 | Diseno definitivo del arbol destino con Alejandro | PENDIENTE |
| 3 | Desarrollo del script Python completo con interfaz Tkinter | PENDIENTE |
| 4 | Configuracion del pipeline GitHub Actions para compilacion del .exe Windows | PENDIENTE |
| 5 | Prueba del .exe en PC de red de la empresa | PENDIENTE |
| 6 | Validacion E2E con carpeta real y ejecucion de organizacion real | PENDIENTE |

---

## Contexto y Decision Arquitectonica

### Descripcion del problema

La empresa Grupo Alvarez gestiona una carpeta en OneDrive (sincronizada
localmente en los PCs de la empresa) con decenas de documentos y subcarpetas
sin jerarquia coherente -- archivos de empresas cliente, documentacion interna,
polizas, contratos y archivos sueltos conviviendo al mismo nivel sin estructura.

El objetivo es una herramienta que:
1. Lea una carpeta origen de forma recursiva (incluyendo subcarpetas).
2. Analice cada archivo con Gemini Vision para determinar su naturaleza y contenido.
3. Genere un informe de organizacion propuesto -- en modo solo lectura, sin mover nada.
4. En fases posteriores: ejecute la organizacion real moviendo los archivos al arbol destino.

### Decision Arquitectonica (validada en S011)

Tras evaluar Power Automate y Microsoft Graph API, se descartaron ambas opciones
por las siguientes razones tecnicas:

- Power Automate: no soporta recursividad nativa en flujos de nube para
  arboles de profundidad variable. La unica alternativa es duplicar manualmente
  bloques para cada nivel, lo que produce flujos fragiles e inmantenibles.
- Microsoft Graph API: requiere registro de aplicacion en Azure AD, gestion
  de OAuth2 corporativo y autenticacion delegada o de aplicacion -- complejidad
  innecesaria dado que OneDrive esta sincronizado localmente.

Solucion elegida: script Python de escritorio que opera integramente sobre
rutas locales del sistema de archivos. OneDrive sincronizado en Windows expone
sus carpetas como rutas locales estandar (C:\Users\Usuario\OneDrive - Empresa\).
Python opera sobre esas rutas con os, pathlib y shutil sin ninguna
autenticacion ni dependencia de Microsoft.

Motor de clasificacion: Gemini Vision (google-genai) analiza cada PDF
y determina a que carpeta del arbol destino pertenece segun su contenido,
nombre y extension.

Distribucion: el .exe se genera en Windows via GitHub Actions (runner
Windows con PyInstaller) y se deposita en una carpeta compartida de red de
la empresa. Todos los PCs acceden y ejecutan directamente desde la red --
sin instalacion, sin descargas individuales, siempre actualizado.

---

## Arquitectura Tecnica

### Stack

- Lenguaje: Python 3.11+
- Interfaz grafica: Tkinter (incluido en Python, sin dependencias extra)
- Motor IA: google-genai -- Gemini Vision (gemini-2.5-flash o equivalente)
- Operaciones de archivo: pathlib, os, shutil
- Compilacion .exe: PyInstaller via GitHub Actions (runner Windows)
- Repositorio: rama o subdirectorio dedicado en el repo de EnterpriseBot

### Flujo de ejecucion (usuario)

1. El usuario abre el .exe desde la carpeta compartida de red.
2. Ventana Tkinter: selector de carpeta origen + visualizacion del arbol destino.
3. Pulsa Analizar -- el script recorre recursivamente la carpeta origen.
4. Cada archivo se envia a Gemini Vision con el prompt de clasificacion.
5. Gemini devuelve la carpeta destino sugerida del arbol predefinido.
6. Al finalizar: se genera un archivo .txt de informe estructurado.
7. El informe se abre automaticamente con el bloc de notas o se guarda
   en la carpeta origen.

### Informe de salida (.txt)

El informe es el entregable principal de la herramienta. Debe ser:
- Legible por una persona sin conocimientos tecnicos.
- Estructurado de forma que sea facilmente indexable.
- Generado siempre en modo solo lectura (no mueve archivos en Paso 1).

Formato del informe:

INFORME DE ORGANIZACION -- [NOMBRE CARPETA ORIGEN]
Fecha: YYYY-MM-DD HH:MM
Total archivos analizados: N

ARBOL DE ORGANIZACION PROPUESTO

[CARPETA DESTINO A]
  archivo_01.pdf    (origen: subcarpeta_x/archivo_01.pdf)
  archivo_02.pdf    (origen: archivo_02.pdf)

[CARPETA DESTINO B]
  archivo_03.pdf    (origen: subcarpeta_y/archivo_03.pdf)

[SIN CLASIFICAR]
  archivo_04.pdf    (motivo: contenido ilegible / baja resolucion)

ARCHIVOS NO PROCESADOS
  archivo_05.pdf    (motivo: error de lectura)

### Arbol destino

El arbol destino se define antes de la ejecucion y se almacena como
configuracion en el propio script o en un archivo JSON adjunto al .exe.
Su diseno definitivo se acuerda con Alejandro en el Paso 2, una vez
validado el concepto con la prueba de campo del Paso 1.

---

## Hoja de Ruta S011

### Paso 1 -- Prueba de campo con carpeta OBSOLETOS

Contexto de la prueba:
- Carpeta: OBSOLETOS -- 80 archivos, 15 subcarpetas, 103 MB.
- Ruta local en el PC de Alejandro:
  C:\Users\Usuario\OneDrive - GRUALDI SL\DC\OBSOLETOS
- Tipo de archivos: PDF en un 99%.
- Modo: solo lectura -- no se mueve ningun archivo.
- Entregable: informe .txt con propuesta de organizacion.

Alcance tecnico del Paso 1. El script de prueba debe:
1. Recorrer recursivamente la carpeta OBSOLETOS con pathlib.Path.rglob.
2. Para cada archivo PDF encontrado:
   a. Leer el archivo en bytes.
   b. Enviarlo a Gemini Vision con el prompt de clasificacion.
   c. Recibir la carpeta destino sugerida y una descripcion breve del contenido.
3. Acumular los resultados en memoria.
4. Generar el informe .txt estructurado al finalizar.
5. Gestionar errores por archivo de forma aislada -- un PDF ilegible no
   interrumpe el procesamiento del resto.

Prompt de clasificacion (borrador -- ajustable tras prueba):
Eres un asistente de clasificacion documental para una empresa del sector
de gruas y maquinaria pesada. Analiza el documento adjunto y determina:
1. CARPETA: La carpeta mas adecuada del arbol donde deberia archivarse.
2. DESCRIPCION: Una descripcion breve (maximo 15 palabras) del contenido.
Responde UNICAMENTE en formato JSON:
{"carpeta": "NOMBRE_CARPETA", "descripcion": "descripcion breve"}

Ejecucion de la prueba:
El script de prueba se ejecuta desde PythonAnywhere con la carpeta OBSOLETOS
comprimida en .zip y subida al servidor, o bien se ejecuta localmente en
el PC de Alejandro si se dispone de Python instalado en ese momento.
La decision de ejecucion se toma al inicio de S011 segun el entorno disponible.

### Paso 2 -- Diseno del arbol destino

Tras revisar el informe de la prueba con Alejandro, se acuerda el arbol
de carpetas destino definitivo. Este arbol se convierte en la configuracion
central de la herramienta.

### Paso 3 -- Script Python completo con Tkinter

Desarrollo del script definitivo con:
- Interfaz grafica Tkinter: selector de carpeta, visualizacion del arbol,
  barra de progreso, log de procesamiento en tiempo real.
- Modo analisis (solo lectura) y modo ejecucion (mueve archivos).
- Configuracion del arbol destino embebida en JSON.
- Gestion robusta de errores y archivos no procesables.
- Logging completo a archivo .log junto al informe .txt.

### Paso 4 -- GitHub Actions: compilacion .exe Windows

Configuracion del workflow de GitHub Actions:
- Runner: windows-latest.
- Pasos: checkout, setup Python, pip install PyInstaller y dependencias,
  pyinstaller, upload artifact como release.
- El .exe resultante se deposita en la carpeta compartida de red de la empresa.

### Paso 5 -- Prueba del .exe en red

Validacion del .exe ejecutandose directamente desde la carpeta compartida
de red en al menos dos PCs de la empresa (sin instalacion local).

### Paso 6 -- Validacion E2E con ejecucion real

Primera ejecucion real (modo ejecucion, no solo lectura) sobre una carpeta
de prueba acordada con Alejandro. Validacion del resultado final.

---

## Archivos Previstos

Nuevos (Neonatos Puros):
- file_organizer/organizer.py -- script principal con logica de clasificacion
- file_organizer/gui.py -- interfaz Tkinter
- file_organizer/config.json -- arbol destino y configuracion
- file_organizer/requirements.in -- dependencias directas
- file_organizer/requirements.txt -- arbol de dependencias compilado
- .github/workflows/build_exe.yml -- workflow GitHub Actions compilacion .exe

Directorio nuevo en el proyecto:
/home/MiguelAeTxio/PROJECTS/EnterpriseBot/file_organizer/
