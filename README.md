# Sistema Edge-to-Cloud para Análisis de Video con CLIP

Este proyecto implementa una arquitectura Edge-to-Cloud para analizar video en tiempo real. Utiliza un modelo de visión artificial base que permite identificar situaciones o elementos sin necesidad de entrenarlo previamente.

El sistema se divide en dos partes:
1. **Cloud Server**: Una API en FastAPI que procesa las imágenes con el modelo de IA y registra los eventos en una base de datos MongoDB.
2. **Edge Client**: Un script en Python (con OpenCV) que captura video desde una cámara local, envía los datos al servidor y muestra los resultados en pantalla.

---

## Instalación y Ejecución

Es necesario encender primero el servidor para que el cliente pueda conectarse.

### 1. Cloud Server

1. Sitúate en la carpeta `/cloud_server`.
2. Opcionalmente, crea y activa un entorno virtual:
   ```bash
   python -m venv venv
   # Windows: venv\Scripts\activate
   # Mac/Linux: source venv/bin/activate
   ```
3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Crea un archivo `.env` basándote en el archivo `.env.template`. Es necesario configurar la variable `MONGO_URI` con los datos de conexión a MongoDB. Y la variable `DB_NAME` con el nombre de la base de datos. En el ejemplo se usa `edge_db`.
5. Ejecuta el servidor:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
   *Nota: La primera ejecución tomará tiempo adicional para descargar el modelo CLIP.*

### 2. Edge Client

1. Abre una nueva terminal y sitúate en la carpeta `/edge_client`.
2. Instala sus dependencias (puedes usar un nuevo entorno virtual):
   ```bash
   pip install -r requirements.txt
   ```
3. Ejecuta el archivo principal:
   ```bash
   python monitor.py
   ```
El script encenderá la cámara, se conectará al servidor y comenzará a mostrar los resultados en la interfaz.

---

## Cómo funciona CLIP (Zero-Shot)

A diferencia de los sistemas de visión estándar que requieren miles de imágenes de ejemplo para aprender a detectar objetos específicos, este proyecto usa CLIP (modelo de OpenAI).

CLIP asocia imágenes y texto. Esto le permite hacer "Zero-Shot Classification", lo que significa que el modelo no ha sido entrenado para el caso de uso particular de la fábrica provisto en el código base. En lugar de eso, le entregamos descripciones en texto ("prompts") de lo que queremos buscar, y el modelo evalúa qué tanto de la imagen coincide con esas descripciones.

Por su naturaleza, el sistema no está limitado al ejemplo actual. Puede usarse para detectar "una persona usando equipo de protección", "un incendio activo" o "alguien levantando peso". El modelo infiere la información a partir del texto indicado sin pasos extra.

---

## Cómo modificar las reglas de detección del sistema

El sistema es dinámico y permite agregar etiquetas personalizadas modificando dos archivos. 

### Paso 1: Servidor (`cloud_server/main.py`)

Abre el archivo `cloud_server/main.py` y localiza el diccionario `ACTION_CONFIG`. Aquí se definen los prompts en inglés (para mayor precisión del modelo).

Puedes agregar tus propias descripciones, configurar si el evento debe considerarse una alarma (`is_alarm`) y cuál es el porcentaje mínimo de certeza requerido (`threshold`).

```python
# Ejemplo en: cloud_server/main.py
ACTION_CONFIG = {
    "A person wearing a hard hat": {"is_alarm": False},
    "A person holding a phone": {"is_alarm": True, "threshold": 0.70},
    "A car approaching fast": {"is_alarm": True, "threshold": 0.60}
}
```

### Paso 2: Cliente (`edge_client/monitor.py`)

Para que el cliente muestre descripciones útiles en pantalla y no el prompt crudo en inglés, abre el archivo `edge_client/monitor.py` y localiza el diccionario `DISPLAY_LABELS`. 

Asigna un texto en español para cada una de las llaves en inglés que creaste en el paso anterior. 

```python
# Ejemplo en: edge_client/monitor.py
DISPLAY_LABELS = {
    "A person wearing a hard hat": "Usando Casco",
    "A person holding a phone": "Alerta: Usando Celular",
    "A car approaching fast": "Alerta: Vehículo Rápido"
}
```
