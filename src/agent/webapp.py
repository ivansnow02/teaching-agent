# main.py
import contextlib
from fastapi import FastAPI


app = FastAPI()



@app.get("/hello")
async def hello():
    """A simple hello world endpoint."""
    return {"message": "Hello, world!"}