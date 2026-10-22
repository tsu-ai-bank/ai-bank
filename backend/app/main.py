from fastapi import FastAPI
app = FastAPI(title="AI-Bank")

@app.get("/api/health")
def health():
    return {"status": "ok"}