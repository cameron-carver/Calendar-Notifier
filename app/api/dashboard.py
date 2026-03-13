"""
Dashboard API endpoints for settings, presets, and metrics.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.brief import UserSettings, FilterPreset
from app.schemas.dashboard import (
    DashboardSettingsRequest,
    DashboardSettingsResponse,
    FilterPresetRequest,
    FilterPresetResponse,
    MetricsResponse
)
from app.services.metrics_service import MetricsService
from app.services.settings_resolver import SettingsResolver

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_or_create_user_settings(db: Session) -> UserSettings:
    """Get the user settings record, creating if it doesn't exist."""
    settings = db.query(UserSettings).first()
    if not settings:
        # Create default settings
        from app.core.config import settings as config
        settings = UserSettings(
            email_address=config.owner_email,
            delivery_time="08:00",
            timezone=config.timezone,
            is_active=True,
            content_depth="standard"  # Set default content depth
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    elif settings.content_depth is None:
        # Update existing settings with default content_depth if missing
        settings.content_depth = "standard"
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/settings", response_model=DashboardSettingsResponse)
async def get_dashboard_settings(db: Session = Depends(get_db)):
    """
    Get all user settings for dashboard UI.

    Returns the current user settings including all feature toggles,
    delivery preferences, and filter configurations.
    """
    settings = get_or_create_user_settings(db)
    return settings


@router.put("/settings", response_model=DashboardSettingsResponse)
async def update_dashboard_settings(
    settings_request: DashboardSettingsRequest,
    db: Session = Depends(get_db)
):
    """
    Update user settings with validation.

    Updates only the fields provided in the request. Fields set to None
    will use global defaults from .env configuration.
    """
    settings = get_or_create_user_settings(db)

    # Update only provided fields
    update_data = settings_request.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    db.commit()
    db.refresh(settings)

    return settings


@router.get("/presets", response_model=List[FilterPresetResponse])
async def list_filter_presets(db: Session = Depends(get_db)):
    """
    Get all saved filter presets.

    Returns all filter presets for the current user, including
    which one is currently active.
    """
    # For single-user setup, user_id = 1
    presets = db.query(FilterPreset).filter(FilterPreset.user_id == 1).all()
    return presets


@router.post("/presets", response_model=FilterPresetResponse)
async def create_filter_preset(
    preset: FilterPresetRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new filter preset.

    Creates a saved filter configuration that can be quickly activated
    to change meeting filtering behavior.
    """
    # Create new preset (not active by default)
    new_preset = FilterPreset(
        user_id=1,  # Single-user setup
        name=preset.name,
        description=preset.description,
        filters=preset.filters,
        is_active=False
    )

    db.add(new_preset)
    db.commit()
    db.refresh(new_preset)

    return new_preset


@router.put("/presets/{preset_id}", response_model=FilterPresetResponse)
async def update_filter_preset(
    preset_id: int,
    preset: FilterPresetRequest,
    db: Session = Depends(get_db)
):
    """
    Update an existing preset.

    Modifies the name, description, or filter configuration of a saved preset.
    """
    db_preset = db.query(FilterPreset).filter(
        FilterPreset.id == preset_id,
        FilterPreset.user_id == 1
    ).first()

    if not db_preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Update fields
    db_preset.name = preset.name
    db_preset.description = preset.description
    db_preset.filters = preset.filters

    db.commit()
    db.refresh(db_preset)

    return db_preset


@router.delete("/presets/{preset_id}")
async def delete_filter_preset(
    preset_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a filter preset.

    Permanently removes a saved preset. Cannot delete an active preset -
    deactivate it first.
    """
    db_preset = db.query(FilterPreset).filter(
        FilterPreset.id == preset_id,
        FilterPreset.user_id == 1
    ).first()

    if not db_preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    if db_preset.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete active preset. Deactivate it first."
        )

    db.delete(db_preset)
    db.commit()

    return {"status": "deleted", "id": preset_id}


@router.post("/presets/{preset_id}/activate")
async def activate_filter_preset(
    preset_id: int,
    db: Session = Depends(get_db)
):
    """
    Activate a specific filter preset.

    Sets the specified preset as active and deactivates all others.
    The active preset's filters will be applied to the next brief generation.
    """
    # Get the preset to activate
    preset = db.query(FilterPreset).filter(
        FilterPreset.id == preset_id,
        FilterPreset.user_id == 1
    ).first()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Deactivate all presets
    db.query(FilterPreset).filter(
        FilterPreset.user_id == 1
    ).update({"is_active": False})

    # Activate the selected preset
    preset.is_active = True

    db.commit()

    return {"status": "activated", "id": preset_id, "name": preset.name}


@router.post("/presets/deactivate")
async def deactivate_all_presets(db: Session = Depends(get_db)):
    """
    Deactivate all filter presets.

    Reverts to using user settings or global defaults for filtering.
    """
    db.query(FilterPreset).filter(
        FilterPreset.user_id == 1
    ).update({"is_active": False})

    db.commit()

    return {"status": "deactivated"}


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get aggregated metrics for usage dashboard.

    Returns statistics about brief generation, API usage, and enrichment
    success rates for the specified time period.

    Args:
        days: Number of days to analyze (default: 30)
    """
    metrics_service = MetricsService()
    aggregated = metrics_service.get_aggregated_metrics(days, db)

    return MetricsResponse(**aggregated)


@router.get("/metrics/trends")
async def get_meeting_trends(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get meeting counts per day for trend visualization.

    Returns daily meeting counts for the specified time period,
    useful for charting meeting activity over time.
    """
    metrics_service = MetricsService()
    trends = metrics_service.get_meeting_trends(days, db)

    return {"trends": trends, "days": days}


@router.get("/resolved-settings")
async def get_resolved_settings(db: Session = Depends(get_db)):
    """
    Get effective settings with inheritance resolved.

    Returns the actual settings that will be used for brief generation,
    showing how global defaults, user settings, and active presets combine.
    """
    user_settings = get_or_create_user_settings(db)

    # Get active preset if any
    active_preset = db.query(FilterPreset).filter(
        FilterPreset.user_id == 1,
        FilterPreset.is_active == True
    ).first()

    # Create resolver
    resolver = SettingsResolver(
        user_settings=user_settings,
        active_preset=active_preset
    )

    # Get all resolved settings
    resolved = resolver.get_all_settings()

    return {
        "resolved_settings": resolved,
        "active_preset": {
            "id": active_preset.id,
            "name": active_preset.name
        } if active_preset else None
    }
