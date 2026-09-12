from fastapi import FastAPI


app = FastAPI(title="Agent Learning API hhy")


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "agent-learning-api",
    }

@app.get("/test")
async def test_endpoint() -> dict[str, str]:
    return {
        "message": "hhy is pig",
    }