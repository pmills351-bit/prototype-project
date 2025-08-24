from fastapi import FastAPI
from pydantic import BaseModel
from src.onnx_predict import predict_one

app = FastAPI(title='Prototype API (ONNX)')

class IrisInput(BaseModel):
    sepal_len: float
    sepal_wid: float
    petal_len: float
    petal_wid: float

@app.get('/health')
def health(): return {'status': 'ok'}

@app.post('/predict')
def predict(inp: IrisInput):
    cls = predict_one([inp.sepal_len, inp.sepal_wid, inp.petal_len, inp.petal_wid])
    return {'class_id': cls}