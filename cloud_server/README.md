# Cloud Inference Server & Dashboard

Este directorio contiene el microservicio backend encargado de la ingesta de imágenes, inferencia de modelos de visión computacional (Zero-Shot Classification) y persistencia de métricas telemétricas. Actúa como el nodo central en la arquitectura *Edge-to-Cloud*, procesando *frames* enviados por clientes ligeros y devolviendo señales de control (alarmas) basadas en umbrales de confianza configurables.

## Arquitectura del Sistema

El servicio está construido sobre un stack asíncrono diseñado para minimizar la latencia de red y el bloqueo de I/O durante la inferencia:

* **API Framework:** FastAPI (ASGI) para el manejo de endpoints y concurrencia.
* **Inference Engine:** PyTorch + Hugging Face `transformers`. Implementa el modelo CLIP (`openai/clip-vit-base-patch32`) para clasificación semántica *zero-shot*.
* **Capa de Persistencia:** MongoDB. Las operaciones de I/O se manejan de forma no bloqueante utilizando el driver asíncrono `motor`.
* **Capa de Presentación:** Renderizado SSR (Server-Side Rendering) mediante Jinja2 para servir el dashboard de telemetría.

---

## Implementación Base

### 1. Inicialización y Gestión de Recursos (`lifespan`)
Dado el alto costo computacional y de memoria del modelo CLIP, los pesos y el procesador se cargan en RAM durante el inicio de la aplicación, evitando latencia en el endpoint de inferencia. Se implementa un mecanismo de caché local para evadir llamadas redundantes al hub de Hugging Face. Las conexiones a la base de datos se agrupan en este mismo contexto.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización del pool de conexiones a MongoDB
    app.state.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    
    # Carga de pesos del modelo (Caché local vs Remote fetch)
    if os.path.exists(LOCAL_MODEL_PATH):
        processor = CLIPProcessor.from_pretrained(LOCAL_MODEL_PATH)
        model = CLIPModel.from_pretrained(LOCAL_MODEL_PATH).to(DEVICE)
    else:
        processor = CLIPProcessor.from_pretrained(MODEL_ID)
        # Lógica de guardado local omitida por brevedad
        ...
```

### 2. Configuración de Inferencia (Zero-Shot Pipeline)
El pipeline clasifica la imagen entrante calculando la similitud del coseno entre los embeddings de la imagen y una lista de *prompts* predefinidos. El diccionario `ACTION_CONFIG` actúa como el esquema de validación, mapeando las clases (texto) con umbrales (`threshold`) específicos y banderas booleanas de estado de alarma (`is_alarm`).

```python
ACTION_CONFIG = {
    "A factory worker focused on working at the desk": {"is_alarm": False},
    "A factory worker distracted looking at a mobile phone": {"is_alarm": True, "threshold": 0.60},
    "A factory worker sleeping on the desk": {"is_alarm": True, "threshold": 0.50},
    "A factory worker drinking water from a glass": {"is_alarm": False}
}
```
*Comportamiento:* Si el tensor de salida arroja una probabilidad mayor al `threshold` definido para una clase marcada con `is_alarm: True`, el endpoint retorna un flag de activación para el hardware Edge. Esta estructura permite extender las clases sin necesidad de reentrenar o hacer *fine-tuning* de los pesos.

### 3. Persistencia Asíncrona de Eventos
Los resultados de la inferencia (probabilidades normalizadas, estado de alarma, timestamp) se estructuran como documentos BSON y se insertan en la colección de eventos de MongoDB. Esta operación delega el I/O al event loop, liberando el thread principal.

```python
db = app.state.db
# Operación no bloqueante para ingesta de telemetría
await db.events.insert_one(log_document)
```

---

## Referencia de Endpoints

* `POST /detect`: Endpoint principal de ingesta. Espera un payload `multipart/form-data` con el archivo de imagen. Devuelve un JSON con la clase detectada, score de confianza y booleano de alarma.
* `GET /dashboard`: Endpoint de presentación. Ejecuta un *aggregation pipeline* en MongoDB para extraer KPIs recientes y renderiza `templates/dashboard.html`.

---

## Entorno y Ejecución

**1. Variables de Entorno**
Crear un archivo `.env` en el directorio raíz del microservicio con las credenciales de la base de datos:

```env
MONGO_URI=mongodb+srv://<user>:<password>@<cluster-url>/?retryWrites=true&w=majority
DB_NAME=edge_vision_db
```

**2. Dependencias**
Se recomienda el uso de un entorno virtual (`venv` o `conda`).
```bash
pip install -r requirements.txt
```

**3. Despliegue Local**
Iniciar el servidor ASGI expuesto en el puerto 8000:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```