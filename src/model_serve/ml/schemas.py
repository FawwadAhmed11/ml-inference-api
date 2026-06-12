from pydantic import BaseModel, model_validator

MIN_FEATURES = 1
MAX_FEATURES = 512


class PredictRequest(BaseModel):
    features: list[float]
    
    
    @model_validator(mode='after')
    def check_input_type(self):
        if len(self.features) < MIN_FEATURES or len(self.features) >= MAX_FEATURES:
            raise ValueError(f'features must have between {MIN_FEATURES} and {MAX_FEATURES} values')
        return self 
    

class PredictResponse(BaseModel):
    prediction: int
    latency_ms: float
    model_version: str 


