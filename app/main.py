from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.api.briefs import router as briefs_router
from app.core.database import engine
from app.models.brief import Base

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="Morning Brief - Calendar Notifier",
    description="An intelligent morning brief tool that automatically sends personalized meeting summaries",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(briefs_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Morning Brief - Calendar Notifier API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "morning-brief"}


@app.get("/info")
async def info():
    """Get API information."""
    return {
        "name": "Morning Brief - Calendar Notifier",
        "version": "1.0.0",
        "description": "Automated morning briefs with calendar integration and AI-powered insights",
        "features": [
            "Google Calendar integration",
            "Affinity CRM integration",
            "News aggregation",
            "AI-powered summarization",
            "Automated email delivery",
            "Customizable scheduling"
        ]
    } 