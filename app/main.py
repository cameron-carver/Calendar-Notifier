from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from app.api.briefs import router as briefs_router
from app.api.dashboard import router as dashboard_router
from app.api.ea import router as ea_router
from app.core.database import engine
from app.models.brief import Base
import os

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
app.include_router(dashboard_router)
app.include_router(ea_router)

# Configure static files and templates
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

# Create directories if they don't exist
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Configure templates
templates = Jinja2Templates(directory=templates_dir)


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


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Render the dashboard UI."""
    return templates.TemplateResponse("dashboard.html", {"request": request}) 