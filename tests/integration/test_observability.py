# tests/integration/test_observability.py
import requests
def test_metrics_exposed(stack):
    # warm up - trigger the latency histogram
    requests.post("http://localhost:8000/v1/predict/json", 
                  json={"features": [1.0]*4})

    r = requests.get("http://localhost:8000/metrics")
    assert r.status_code == 200
    for metric in ("predictions_total", "prediction_latency_seconds", "model_info"):
        assert metric in r.text