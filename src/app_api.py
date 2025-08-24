from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title='Prototype API')

class Echo(BaseModel):
    text: str

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.post('/echo')
def echo(payload: Echo):
    return {'you_said': payload.text}