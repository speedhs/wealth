import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router
from app.core.db import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Kalpi Trade Execution Engine",
    description="Engine to automatically validate, enqueue, and execute portfolio orders.",
    version="1.0.0"
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event to initialize DB schema
@app.on_event("startup")
def startup_event():
    logger.info("Initializing application...")
    try:
        init_db()
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")

# Include API Router under /api prefix
app.include_router(api_router, prefix="/api")

# Serve the visual dashboard
@app.get("/")
def get_dashboard():
    return FileResponse("frontend/index.html")

# Mount frontend files (CSS/JS) under /static
app.mount("/static", StaticFiles(directory="frontend"), name="static")
