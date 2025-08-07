from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from app.core.database import get_db
from app.services.brief_service import BriefService
from app.schemas.brief import BriefRequest, BriefResponse, UserSettingsRequest, UserSettingsResponse
from app.models.brief import Brief

router = APIRouter(prefix="/briefs", tags=["briefs"])


@router.post("/generate", response_model=BriefResponse)
async def generate_brief(
    request: BriefRequest,
    db: Session = Depends(get_db)
):
    """Generate a morning brief for the specified date."""
    try:
        brief_service = BriefService()
        brief_response = await brief_service.generate_daily_brief(request.date)
        
        # Save to database
        brief = brief_service.save_brief_to_database(brief_response, db)
        brief_response.id = brief.id
        
        return brief_response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating brief: {str(e)}")


@router.post("/generate-and-send")
async def generate_and_send_brief(
    request: BriefRequest,
    db: Session = Depends(get_db)
):
    """Generate and send a morning brief."""
    try:
        brief_service = BriefService()
        
        # Get user settings
        user_settings = brief_service.get_user_settings(db)
        if not user_settings:
            raise HTTPException(status_code=400, detail="No user settings configured")
        
        # Generate and send
        success = await brief_service.generate_and_send_brief(
            user_settings.email_address,
            request.date
        )
        
        if success:
            return {"message": "Brief generated and sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send brief")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/history", response_model=List[BriefResponse])
async def get_brief_history(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get recent brief history."""
    try:
        brief_service = BriefService()
        briefs = brief_service.get_brief_history(db, limit)
        
        # Convert to response models
        brief_responses = []
        for brief in briefs:
            brief_responses.append(BriefResponse(
                id=brief.id,
                date=brief.date,
                content=brief.content,
                events_summary=brief.events_summary,
                created_at=brief.created_at,
                is_sent=brief.is_sent
            ))
        
        return brief_responses
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving brief history: {str(e)}")


@router.get("/{brief_id}", response_model=BriefResponse)
async def get_brief(
    brief_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific brief by ID."""
    try:
        brief = db.query(Brief).filter(Brief.id == brief_id).first()
        if not brief:
            raise HTTPException(status_code=404, detail="Brief not found")
        
        return BriefResponse(
            id=brief.id,
            date=brief.date,
            content=brief.content,
            events_summary=brief.events_summary,
            created_at=brief.created_at,
            is_sent=brief.is_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving brief: {str(e)}")


@router.put("/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    settings: UserSettingsRequest,
    db: Session = Depends(get_db)
):
    """Update user settings."""
    try:
        brief_service = BriefService()
        updated_settings = brief_service.update_user_settings(settings.dict(), db)
        
        return UserSettingsResponse(
            id=updated_settings.id,
            delivery_time=updated_settings.delivery_time,
            timezone=updated_settings.timezone,
            email_address=updated_settings.email_address,
            is_active=updated_settings.is_active,
            created_at=updated_settings.created_at,
            updated_at=updated_settings.updated_at
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")


@router.get("/settings", response_model=UserSettingsResponse)
async def get_user_settings(
    db: Session = Depends(get_db)
):
    """Get current user settings."""
    try:
        brief_service = BriefService()
        settings = brief_service.get_user_settings(db)
        
        if not settings:
            raise HTTPException(status_code=404, detail="No user settings found")
        
        return UserSettingsResponse(
            id=settings.id,
            delivery_time=settings.delivery_time,
            timezone=settings.timezone,
            email_address=settings.email_address,
            is_active=settings.is_active,
            created_at=settings.created_at,
            updated_at=settings.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving settings: {str(e)}") 