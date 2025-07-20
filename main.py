from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, allegro

app = FastAPI(title="Allegro Connect API", version="1.0.0")

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth.router)
app.include_router(allegro.router)

@app.get("/")
async def root():
    return {"message": "Allegro Connect API is running"}


# Две пустые строки перед этим блоком по стандарту PEP 8
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)