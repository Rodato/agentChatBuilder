"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from core.config import settings
from core.orchestrator import Orchestrator

# Initialize app
app = FastAPI(
    title="Agent Chat Builder",
    description="Platform for building chatbots with specialized agents",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator
orchestrator = Orchestrator()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Agent Chat Builder",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.app_env,
    }


@app.post("/chat")
async def chat(message: str, user_id: str = None, conversation_id: str = None):
    """
    Process a chat message through the agent pipeline.

    Args:
        message: User message
        user_id: Optional user identifier
        conversation_id: Optional conversation identifier

    Returns:
        Agent response with metadata
    """
    result = orchestrator.process_query(
        user_input=message,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    return {
        "response": result["response"],
        "agent_used": result["agent_used"],
        "intent": result["intent"],
        "language": result["language"],
        "processing_time_ms": result["processing_time_ms"],
    }


# Import and include routers
from api.routes.bots import router as bots_router
from api.routes.agents import router as agents_router

app.include_router(bots_router, prefix="/api/bots", tags=["bots"])
app.include_router(agents_router, prefix="/api/bots", tags=["agents"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.app_debug,
    )
