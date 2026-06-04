from fastapi import FastAPI, HTTPException, status, UploadFile, Request
from fastapi.responses import JSONResponse, Response
from contextlib import asynccontextmanager
import torch
import torchvision.models as models
from prometheus_client import Counter, Histogram, make_asgi_app, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_fastapi_instrumentator import Instrumentator
import time
import os
import logging
from log_config import setup_json_logging
import sys
from datetime import datetime
import redis
import json
import asyncio
import joblib
from pydantic import BaseModel 
from PIL import Image
from config import settings
import torchvision.transforms as transforms
import io
import uuid
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from contextvars import ContextVar
from middleware import track_in_flight_requests, add_request_id, check_body_size, request_id_var










# Rate limiter
MODEL_NAME = os.getenv("MODEL_NAME", "ResNet-18")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v3")
# Initialize redis for storage and Limiter
# storage = RedisStorage("redis://redis:6379")
limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379")

# 1. Define the Gauge metrics
# Track current requests using labels for method and endpoint

MODEL_INFO = Gauge(
    "model_info",
    "Metadata about the deployed FastAPI model version",
    ["version", "model_name", "framework"]
)



MODEL_INFO.labels(version=MODEL_VERSION, model_name=MODEL_NAME, framework="pytorch").set(1)
# Metrics
predictions = Counter(
    'predictions_total',
    'Total number of predictions',
    labelnames=['class_id']
)
latency = Histogram('prediction_latency_seconds', 'Prediction latency')
# Add metrics endpoint



# Setup file logging
log_dir = "logs"

model_confidence = Histogram(
    'model_prediction_confidence',
    'Prediction confidence scores'
)

# os.environ["BATCH_SIZE"] = "128"

model = None

# Connect to Redis
redis_client = redis.Redis(
    host='redis',  # Service name from docker-compose
    port=6379,
    decode_responses=True
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    # Code here runs BEFORE the application starts receiving requests
    print("Application is loading up...")    
    # print(os.getcwd())
    model = await asyncio.to_thread(torch.load, settings.MODEL_PATH, weights_only=False)
    app.state.model = model
    app.state.model_version = settings.MODEL_VERSION
    yield  # The application runs while paused here
    # --- SHUTDOWN LOGIC ---
    # Code here runs AFTER the application finishes handling requests
    print("Application is shutting down...")
    
app = FastAPI(lifespan=lifespan)

setup_json_logging()
logger = logging.getLogger("app_logger")


app = FastAPI(lifespan=lifespan)
# Middleware
app.middleware("http")(track_in_flight_requests)
app.middleware("http")(add_request_id)
app.middleware("http")(check_body_size)

# Register the error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# prometheus instrumentor
Instrumentator(
    should_group_status_codes=False,
).instrument(app).expose(app)



def preprocess(image_bytes: bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])
    return transform(image).unsqueeze(0)  # add batch dimension

# def send_response(res):

#     return 


@app.post("/v1/predict")
async def predict(image: UploadFile):
    start_time = time.time()
    try: 
        model = app.state.model
        if model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")
        # load image
        image_bytes = await image.read()
        tensor = await asyncio.to_thread(preprocess, image_bytes)
        # perform prediction
        with torch.no_grad():
            output = await asyncio.to_thread(model, tensor)
            predicted = output.argmax(1).item()
        
        result = {
            "prediction": predicted,
            "latency_ms": (time.time() - start_time) * 1000 
        }
        predictions.labels(class_id=predicted).inc()
        return result
    

    except Exception as e:
        logger.error(f"prediction failed : {e}")
        raise HTTPException(500, str(e))

    finally:
        latency.observe(time.time() - start_time)
        
        
        



@app.post("/v1/predict/batch")
async def BatchRequest(inputs: list[UploadFile]):
    start_time = time.time()
    try:
        
        batch = []
        model = app.state.model
        results = []
        if model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")
        

        for image in inputs:
            row_start = time.time()
            image_bytes = await image.read()
            tensor = await asyncio.to_thread(preprocess, image_bytes)
            batch.append((tensor, row_start))
            if len(batch) >= int(os.environ.get("BATCH_SIZE", 128)):
                tensors = [t for t, _ in batch]
                start_times = [s for _, s in batch]
                output = model(torch.cat(tensors, dim=0))
                preds = output.argmax(1).tolist()

                for pred, row_start in zip(preds, start_times):
                    results.append({
                        "prediction": pred,
                        "latency_ms": (time.time() - row_start) * 1000
                    })
                    predictions.labels(class_id=pred).inc()
                batch = []

        if batch: 
            tensors = [t for t, _ in batch]
            start_times = [s for _, s in batch]
            output = model(torch.cat(tensors, dim=0))
            preds = output.argmax(1).tolist()
            for pred, row_start in zip(preds, start_times):
                results.append({
                    "prediction": pred,
                    "latency_ms": (time.time() - row_start) * 1000
                })
                predictions.labels(class_id=pred).inc()
        

        return results

    except Exception as e:
        logger.error(f"prediction failed : {e}")
        raise HTTPException(500, str(e))

    finally:
        latency.observe(time.time() - start_time)



#Get
custom_rate_limit = os.environ.get("custom_rate_limit", "5/minute")

@app.get("/")
@limiter.limit(custom_rate_limit)

def root():
    logger.info("Root endpoint was accessed successfully, logger works")
    logger.info(f"Request_id: {request_id_var.get()}")

    return {
        "message": "ML Model API -- New API v2.0",
        "model": MODEL_NAME,
        "version": MODEL_VERSION,
        "framework": "pytorch"
    }


@app.get("/health")
@limiter.limit(custom_rate_limit)
def health(request: Request):
    
    # raise HTTPException(
    #     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #     detail="Something went wrong internally"
    # )
    current_request_id = request.state.request_id
    logger.info(f"Request_id: {request_id_var.get()}")
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "request_id": current_request_id,
        "torch_version": torch.__version__,

    }


request_count = Counter(
    'ml_api_requests_total',
    'Total API requests',
    ['endpoint', 'status']
)

request_duration = Histogram(
    'ml_api_request_duration_seconds',
    'Request duration in seconds',
    ['endpoint']
)


@app.get("/info")
@limiter.limit(custom_rate_limit)
def info(request: Request):
    logger.info("Info endpoint called")
    logger.info(f"Request_id: {request_id_var.get()}")
    start_time = time.time()
    
    try:
        # Check cache
        cache_key = "model_info"
        cached = redis_client.get(cache_key)

        if cached:
            logger.info("Returning cached response")
            return json.loads(cached)
        
        if model is None:
            return {"error": "Model not loaded"}

        # Count parameters
        params = sum(p.numel() for p in model.parameters())

        result =  {
            "model": "ResNet-18",
            "parameters": params,
            "device": "cpu",
            "cached": False
        }
        request_count.labels(endpoint='info', status='success').inc()
        redis_client.setex(cache_key, 60, json.dumps(result))
        logger.info("Generated and cached response")
        return result
    
    except Exception as e:
        request_count.labels(endpoint='info', status='error').inc()
        raise
    finally:
        duration = time.time() - start_time
        request_duration.labels(endpoint='info').observe(duration)