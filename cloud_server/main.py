import io
import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch
import motor.motor_asyncio
from dotenv import load_dotenv
from pathlib import Path

# Carga de variables de entorno
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEVICE = "cpu"
MODEL_ID = "openai/clip-vit-base-patch32"
LOCAL_MODEL_PATH = "./model"
DEFAULT_THRESHOLD = 0.60

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "edge_vision_db")

# Configuración de plantillas HTML
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ACTION_CONFIG = {
    "A factory worker focused on working at the desk": {"is_alarm": False},
    "A factory worker distracted looking at a mobile phone": {"is_alarm": True, "threshold": 0.60},
    "A factory worker sleeping on the desk": {"is_alarm": True, "threshold": 0.50},
    "A factory worker drinking water from a glass": {"is_alarm": False}
}

LABELS = list(ACTION_CONFIG.keys())

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona la carga del modelo IA y la conexión a MongoDB al inicio.
    """
    logger.info("Iniciando conexión a MongoDB...")
    try:
        app.state.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        app.state.db = app.state.mongo_client[DB_NAME]
        logger.info("Conectado a MongoDB Atlas exitosamente.")
    except Exception as e:
        logger.error(f"Fallo al conectar a MongoDB: {e}")
        raise e

    logger.info("Iniciando carga del modelo CLIP...")
    try:
        if os.path.exists(LOCAL_MODEL_PATH):
            logger.info("Cargando modelo desde caché local...")
            processor = CLIPProcessor.from_pretrained(LOCAL_MODEL_PATH)
            model = CLIPModel.from_pretrained(LOCAL_MODEL_PATH).to(DEVICE)
        else:
            logger.info("Descargando modelo de la nube...")
            processor = CLIPProcessor.from_pretrained(MODEL_ID)
            model = CLIPModel.from_pretrained(MODEL_ID).to(DEVICE)
            processor.save_pretrained(LOCAL_MODEL_PATH)
            model.save_pretrained(LOCAL_MODEL_PATH)
            
        app.state.model = model
        app.state.processor = processor
    except Exception as e:
        logger.error(f"Fallo crítico al cargar el modelo: {e}")
        raise e
        
    yield
    
    logger.info("Cerrando conexiones...")
    app.state.mongo_client.close()

app = FastAPI(title="Edge-to-Cloud Distraction Detection", lifespan=lifespan)

@app.post("/detect")
async def detect_distraction(file: UploadFile = File(...)):
    """
    Procesa la imagen, evalúa reglas de negocio y registra el evento en MongoDB.
    """
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")

        processor = app.state.processor
        model = app.state.model

        inputs = processor(text=LABELS, images=image, return_tensors="pt", padding=True).to(DEVICE)
        
        with torch.no_grad():
            outputs = model(**inputs)
            
        logits_per_image = outputs.logits_per_image
        probs = logits_per_image.softmax(dim=1).cpu().numpy()[0]
        
        all_scores = {LABELS[i]: float(probs[i]) for i in range(len(LABELS))}
        
        max_index = probs.argmax()
        winning_label = LABELS[max_index]
        winning_score = float(probs[max_index])
        
        action_rules = ACTION_CONFIG[winning_label]
        is_configured_as_alarm = action_rules.get("is_alarm", False)
        required_threshold = action_rules.get("threshold", DEFAULT_THRESHOLD)
        
        trigger_alarm = is_configured_as_alarm and (winning_score > required_threshold)
        
        # Preparar documento para MongoDB
        log_document = {
            "timestamp": datetime.utcnow(),
            "action_detected": winning_label,
            "confidence": winning_score,
            "is_alarm": trigger_alarm,
            "all_scores": all_scores
        }
        
        # Insertar en base de datos de forma asíncrona
        db = app.state.db
        await db.events.insert_one(log_document)
            
        return JSONResponse(content={
            "alarm": trigger_alarm,
            "action_detected": winning_label,
            "confidence_score": winning_score,
            "all_scores": all_scores
        })

    except Exception as e:
        logger.error(f"Error procesando: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Fallo interno en el procesamiento."})

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """
    Genera y sirve el panel de control HTML con KPIs extraídos de MongoDB.
    """
    db = request.app.state.db
    
    # Consultas a MongoDB para KPIs
    total_events = await db.events.count_documents({})
    total_alarms = await db.events.count_documents({"is_alarm": True})
    
    # Agregación para obtener la acción más frecuente
    pipeline = [
        {"$group": {"_id": "$action_detected", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1}
    ]
    cursor = db.events.aggregate(pipeline)
    most_common = await cursor.to_list(length=1)
    most_common_action = most_common[0]["_id"] if most_common else "N/A"
    
    # Obtener los últimos 20 registros
    recent_logs_cursor = db.events.find({}, {"_id": 0}).sort("timestamp", -1).limit(20)
    recent_logs = await recent_logs_cursor.to_list(length=20)
    
    # Formateo de fechas para la plantilla
    for log in recent_logs:
        log["timestamp"] = log["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

    kpis = {
        "total_events": total_events,
        "total_alarms": total_alarms,
        "most_common_action": most_common_action
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "kpis": kpis,
            "recent_logs": recent_logs
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)