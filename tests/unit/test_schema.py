import pytest
from model_serve.ml.schemas import PredictRequest 

def test_rejects_wrong_feature_count():
    with pytest.raises(ValueError):
        PredictRequest(features=[])

def test_normalize_impodent():
    raw = PredictRequest(features=[1.0]*4)
    assert raw == PredictRequest.model_validate(raw.model_dump())