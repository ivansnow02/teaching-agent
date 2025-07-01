# main.py
import contextlib
from fastapi import FastAPI

from fastapi import Request

app = FastAPI()


@app.get("/hello")
async def hello():
    """A simple hello world endpoint."""
    return {"message": "Hello, world!"}
