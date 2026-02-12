"""
FastAPI gateway for Prefect integration.
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time

from core.config import get_settings
from core.prefect_client import get_prefect_client
from api.v1.router import router as api_v1_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    print("🚀 Starting FastAPI Gateway...")
    print(f"📡 Prefect API: {settings.prefect_api_url}")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down FastAPI Gateway...")
    client = await get_prefect_client()
    await client.close()


app = FastAPI(
    title="Django Prefect Gateway",
    description="API Gateway for Prefect flow orchestration",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Include API router
app.include_router(api_v1_router, prefix="/api/v1")

@app.get("/", tags=["health"])
async def root():
    """Root endpoint."""
    return {
        "message": "Django Prefect Gateway",
        "status": "running",
        "version": "0.1.0",
        "docs": "/docs",
    }

@app.get("/health", tags=["health"])
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "prefect_api": settings.prefect_api_url,
    }

@app.get("/ready", tags=["health"])
async def ready():
    """Readiness check endpoint."""
    try:
        client = await get_prefect_client()
        await client.list_deployments(limit=1)
        return {"status": "ready", "prefect": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not ready", "error": str(e)},
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)