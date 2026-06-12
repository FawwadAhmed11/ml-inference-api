def test_health_always_200(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"



# # tests/contract/test_predict.py
# def test_predict_returns_expected_shape(client):
#     r = client.post("/v1/predict", json={"features":[1.0]*4})
#     assert r.status_code == 200
#     body = r.json()
#     assert set(body.keys()) == {"prediction", "latency_ms", "model_version"}