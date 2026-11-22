"""FastAPI app. Slice 0: health only."""

from fastapi import FastAPI

app = FastAPI(title="getpaid-agent API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
