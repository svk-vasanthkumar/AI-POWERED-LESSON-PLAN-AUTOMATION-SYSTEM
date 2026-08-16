from fastapi import FastAPI

app = FastAPI(title="LPS Backend")


@app.get("/")
def read_root():
    return {"message": "LPS backend is running"}
