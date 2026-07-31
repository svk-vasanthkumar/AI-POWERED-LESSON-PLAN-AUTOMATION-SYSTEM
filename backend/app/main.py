from fastapi import FastAPI

app = FastAPI(
    title="AI Lesson Plan Automation API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {
        "message": "Welcome to AI Lesson Plan Automation API"
    }

@app.get("/health")
def health():
    return {
        "status": "OK"
    }