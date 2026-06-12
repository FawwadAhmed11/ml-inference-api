# ml-inference-api

Production-grade ML inference service built on FastAPI, containerized with Docker, and deployed on Kubernetes. Serves ResNet-18 image classification with full observability, rate limiting, request validation, and horizontal autoscaling.

---

## What This Is

A complete model serving system built from scratch — not a tutorial clone. The goal was to build the kind of inference API that would exist at a real AI company: multi-stage Docker builds, Kubernetes deployments with HPA, Prometheus metrics, structured JSON logging with request tracing, Redis caching, and middleware for rate limiting and payload validation.

---

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │           Kubernetes Cluster          │
                        │                                       │
  Client ──────────────►│  Service (LoadBalancer)               │
                        │       │                               │
                        │       ▼                               │
                        │  ┌─────────┐  ┌─────────┐            │
                        │  │ ml-api  │  │ ml-api  │  (HPA)     │
                        │  │  pod    │  │  pod    │  2-10       │
                        │  └────┬────┘  └────┬────┘            │
                        │       │             │                 │
                        │       ▼             ▼                 │
                        │  ┌──────────────────────┐            │
                        │  │       Redis           │            │
                        │  │   (response cache)    │            │
                        │  └──────────────────────┘            │
                        │                                       │
                        │  ┌──────────┐  ┌─────────┐           │
                        │  │Prometheus│  │ Grafana │           │
                        │  └──────────┘  └─────────┘           │
                        └─────────────────────────────────────┘
```

---

## Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| ML Model | PyTorch ResNet-18 (ImageNet) |
| Containerization | Docker (multi-stage, non-root, 267MB) |
| Orchestration | Kubernetes + Minikube |
| Autoscaling | HPA (CPU + memory targets) |
| Caching | Redis 7 |
| Metrics | Prometheus + Grafana + prometheus-fastapi-instrumentator |
| Rate Limiting | slowapi + Redis storage |
| Logging | python-json-logger + contextvars request tracing |

---

## API Endpoints

### `POST /v1/predict`
Single image inference. Accepts a multipart image upload, returns predicted ImageNet class ID and end-to-end latency.

```bash
curl -X POST http://localhost:8000/v1/predict \
  -F "image=@image.jpg"
```

```json
{
  "prediction": 463,
  "latency_ms": 42.3
}
```

### `POST /v1/predict/batch`
Batch inference up to 128 images. Images are stacked into a single tensor and processed in one forward pass. Returns per-row latency for each image.

```bash
curl -X POST http://localhost:8000/v1/predict/batch \
  -F "inputs=@img1.jpg" \
  -F "inputs=@img2.jpg" \
  -F "inputs=@img3.jpg"
```

```json
[
  {"prediction": 463, "latency_ms": 77.9},
  {"prediction": 463, "latency_ms": 70.8},
  {"prediction": 463, "latency_ms": 67.9}
]
```

### `GET /health`
Liveness check. Returns model load status, torch version, and current request ID.

### `GET /metrics`
Prometheus scrape endpoint. Exposes custom metrics + auto-instrumented FastAPI request histograms.

### `GET /info`
Model metadata with Redis caching (60s TTL).

---

## Middleware Stack

Three middleware layers run on every request in order:

**1. Request ID** — generates or propagates `X-Request-Id` UUID. Stored in `contextvars` so it's automatically injected into every log line without passing it explicitly.

**2. Body Size** — rejects payloads over 1MB with HTTP 413 before the request body is read.

**3. Rate Limiting** — `slowapi` keyed by client IP, backed by Redis so limits are shared across all pod replicas. Configurable via `RATE_LIMIT` env var (default: 5/minute).

---

## Observability

### Custom Prometheus Metrics

| Metric | Type | Description |
|---|---|---|
| `predictions_total{class_id}` | Counter | Predictions by ImageNet class |
| `prediction_latency_seconds` | Histogram | End-to-end inference latency |
| `http_requests_in_flight{method,handler}` | Gauge | Concurrent requests per endpoint |
| `model_info{version,model_name,framework}` | Gauge | Deployed model metadata |

Plus full auto-instrumented FastAPI metrics from `prometheus-fastapi-instrumentator`:
- `http_requests_total{handler,method,status}`
- `http_request_duration_seconds{handler,method}`
- `http_request_size_bytes` / `http_response_size_bytes`

### Structured JSON Logging

Every log line is JSON with `request_id` automatically injected via a logging filter reading from `contextvars`:

```json
{
  "timestamp": "2026-06-04T23:03:43Z",
  "level": "INFO",
  "name": "app_logger",
  "message": "Info endpoint called",
  "request_id": "c92ac027-3735-4612-8848-00acfbe16cd5"
}
```

---

## Running Locally

### Docker Compose (recommended)

```bash
git clone https://github.com/FawwadAhmed11/ml-inference-api.git
cd ml-inference-api

# Add your model weights (not included in repo)
# Place resnet18.pth in src/model_serve/models/

docker-compose up --build
```

Services:
- API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin)

### Kubernetes (Minikube)

```bash
# Build image inside minikube's Docker daemon
eval $(minikube docker-env)
docker build -t ml-inference-api:v1 .

# Deploy
kubectl apply -f src/configmap.yaml
kubectl apply -f src/deployment.yaml
kubectl apply -f src/service.yaml
kubectl apply -f src/hpa.yaml

# Access
minikube service ml-api-service --url
```



---
## Testing

### Unit tests
Fast, no external dependencies. Tests schema validation logic.
```bash
pytest tests/unit/ -v
```

### Integration tests
Spins up the full Docker Compose stack via testcontainers, runs real HTTP traffic, verifies metrics are exposed end-to-end. Requires Docker.
```bash
pytest tests/integration/ -v
```

### Run all tests
```bash
pytest -v
```
---

## Kubernetes Configuration

**Deployment:** 2 replicas, rolling update strategy (25% max surge), liveness + readiness probes on `/health`.

**HPA:** Scales 2–10 replicas. Triggers at 70% CPU or 80% memory.

**Resources per pod:**
```
requests: 250m CPU, 512Mi memory
limits:   500m CPU, 2Gi memory
```

**ConfigMap-driven config:** `MODEL_PATH`, `MODEL_NAME`, `DEVICE`, `BATCH_SIZE`, `RATE_LIMIT` — no hardcoded values in the image.

---

## Docker Image

Multi-stage build: builder stage installs PyTorch + dependencies, runtime stage copies only the installed packages. Runs as non-root `appuser`.

```
Image size: 267MB
User: appuser (non-root)
Base: python:3.11-slim
```

---

## Project Structure

```
ml-inference-api/
├── Dockerfile                    # Multi-stage build, non-root appuser, ~280MB
├── docker-compose.yaml           # Full stack: API + Redis + Prometheus + Grafana
├── prometheus.yaml               # Prometheus scrape config
├── pyproject.toml                # Package config + pytest settings
├── requirements.txt
└── src/
    ├── configmap.yaml            # K8s ConfigMap
    ├── deployment.yaml           # K8s Deployment, 2 replicas, rolling update
    ├── service.yaml              # K8s LoadBalancer Service
    ├── hpa.yaml                  # HPA: 2-10 replicas, 70% CPU / 80% memory
    └── model_serve/
        ├── app.py                # FastAPI app, endpoints, metrics, APIRouter
        ├── config.py             # Pydantic BaseSettings
        ├── log_config.py         # JSON logging + RequestIdFilter
        ├── middleware.py         # Request ID (contextvars), body size, in-flight gauge
        └── ml/
            └── schemas.py        # PredictRequest + PredictResponse Pydantic models
└── tests/
    ├── unit/
    │   └── test_schema.py        # Schema validation unit tests
    ├── contract/
    │   ├── conftest.py           # TestClient fixture with mocked model + Redis
    │   └── test_predict.py
    └── integration/
        ├── conftest.py           # testcontainers DockerCompose fixture
        └── test_observability.py # Verifies metrics endpoint end-to-end
```


---

## Key Design Decisions

**Why `app.state` over globals for model storage** — globals are module-level and shared across the process. `app.state` is the FastAPI-idiomatic pattern and makes the model accessible in request handlers without imports.

**Why `asyncio.to_thread` for inference** — `torch.load` and model forward passes are CPU-bound and block the event loop. Offloading to a thread pool keeps the async server responsive during inference.

**Why Redis-backed rate limiting** — in-memory rate limiting breaks with multiple replicas since each pod tracks its own counters. Redis gives all pods a shared counter, so limits actually hold at scale.

**Why `contextvars` for request ID propagation** — avoids passing `request_id` as a parameter through every function call. Each async coroutine gets its own isolated copy of the context, so concurrent requests don't bleed into each other's log lines.