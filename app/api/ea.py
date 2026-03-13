"""
EA Mode API Router.

Provides REST endpoints for managing executives, meeting annotations,
and person relationships in Executive Assistant mode.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.services.executive_service import ExecutiveService
from app.services.annotation_service import AnnotationService
from app.services.relationship_service import RelationshipService
from app.schemas.ea import (
    ExecutiveCreate, ExecutiveUpdate, ExecutiveResponse,
    AnnotationCreate, AnnotationUpdate, AnnotationResponse,
    RelationshipCreate, RelationshipUpdate, RelationshipResponse
)

router = APIRouter(prefix="/ea", tags=["EA Mode"])


# ============================================================================
# EXECUTIVE ENDPOINTS
# ============================================================================

@router.post("/executives", response_model=ExecutiveResponse, status_code=201)
def create_executive(
    executive: ExecutiveCreate,
    db: Session = Depends(get_db)
):
    """Create a new executive profile."""
    service = ExecutiveService(db)

    try:
        created = service.create_executive(
            name=executive.name,
            email=executive.email,
            google_calendar_ids=executive.google_calendar_ids,
            title=executive.title,
            timezone=executive.timezone,
            delivery_time=executive.delivery_time
        )
        return created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/executives", response_model=List[ExecutiveResponse])
def list_executives(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List all executives."""
    service = ExecutiveService(db)
    return service.list_executives(active_only=active_only)


@router.get("/executives/{executive_id}", response_model=ExecutiveResponse)
def get_executive(
    executive_id: int,
    db: Session = Depends(get_db)
):
    """Get executive by ID."""
    service = ExecutiveService(db)
    executive = service.get_executive(executive_id)

    if not executive:
        raise HTTPException(status_code=404, detail="Executive not found")

    return executive


@router.put("/executives/{executive_id}", response_model=ExecutiveResponse)
def update_executive(
    executive_id: int,
    updates: ExecutiveUpdate,
    db: Session = Depends(get_db)
):
    """Update executive profile."""
    service = ExecutiveService(db)

    update_dict = updates.dict(exclude_unset=True)
    executive = service.update_executive(executive_id, **update_dict)

    if not executive:
        raise HTTPException(status_code=404, detail="Executive not found")

    return executive


@router.delete("/executives/{executive_id}", status_code=204)
def delete_executive(
    executive_id: int,
    hard_delete: bool = False,
    db: Session = Depends(get_db)
):
    """Delete executive (soft delete by default)."""
    service = ExecutiveService(db)

    if hard_delete:
        success = service.hard_delete_executive(executive_id)
    else:
        success = service.delete_executive(executive_id)

    if not success:
        raise HTTPException(status_code=404, detail="Executive not found")


@router.post("/executives/{executive_id}/calendars", response_model=ExecutiveResponse)
def add_calendar(
    executive_id: int,
    calendar_id: str,
    db: Session = Depends(get_db)
):
    """Add calendar to executive's calendar list."""
    service = ExecutiveService(db)

    # TODO: Validate calendar access before adding
    executive = service.add_calendar(executive_id, calendar_id)

    if not executive:
        raise HTTPException(status_code=404, detail="Executive not found")

    return executive


@router.delete("/executives/{executive_id}/calendars/{calendar_id}", response_model=ExecutiveResponse)
def remove_calendar(
    executive_id: int,
    calendar_id: str,
    db: Session = Depends(get_db)
):
    """Remove calendar from executive's calendar list."""
    service = ExecutiveService(db)
    executive = service.remove_calendar(executive_id, calendar_id)

    if not executive:
        raise HTTPException(status_code=404, detail="Executive not found")

    return executive


# ============================================================================
# ANNOTATION ENDPOINTS
# ============================================================================

@router.post("/executives/{executive_id}/annotations", response_model=AnnotationResponse, status_code=201)
def create_annotation(
    executive_id: int,
    annotation: AnnotationCreate,
    db: Session = Depends(get_db)
):
    """Create or update annotation for a meeting."""
    service = AnnotationService(db)

    created = service.create_annotation(
        executive_id=executive_id,
        event_id=annotation.event_id,
        priority=annotation.priority.value,
        prep_notes=annotation.prep_notes,
        action_before_meeting=annotation.action_before_meeting
    )

    return created


@router.get("/executives/{executive_id}/annotations", response_model=List[AnnotationResponse])
def list_annotations(
    executive_id: int,
    priority: Optional[str] = None,
    has_follow_up: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """List all annotations for an executive."""
    service = AnnotationService(db)
    return service.list_annotations(
        executive_id=executive_id,
        priority=priority,
        has_follow_up=has_follow_up
    )


@router.get("/executives/{executive_id}/annotations/{event_id}", response_model=AnnotationResponse)
def get_annotation(
    executive_id: int,
    event_id: str,
    db: Session = Depends(get_db)
):
    """Get annotation for a specific meeting."""
    service = AnnotationService(db)
    annotation = service.get_annotation(executive_id, event_id)

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    return annotation


@router.put("/executives/{executive_id}/annotations/{event_id}", response_model=AnnotationResponse)
def update_annotation(
    executive_id: int,
    event_id: str,
    updates: AnnotationUpdate,
    db: Session = Depends(get_db)
):
    """Update meeting annotation."""
    service = AnnotationService(db)

    # Get existing annotation
    annotation = service.get_annotation(executive_id, event_id)
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Update fields
    update_dict = updates.dict(exclude_unset=True)
    # Convert enum to string
    if 'priority' in update_dict:
        update_dict['priority'] = update_dict['priority'].value

    updated = service.update_annotation(annotation.id, **update_dict)
    return updated


@router.delete("/executives/{executive_id}/annotations/{event_id}", status_code=204)
def delete_annotation(
    executive_id: int,
    event_id: str,
    db: Session = Depends(get_db)
):
    """Delete meeting annotation."""
    service = AnnotationService(db)
    annotation = service.get_annotation(executive_id, event_id)

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    service.delete_annotation(annotation.id)


@router.post("/executives/{executive_id}/annotations/{event_id}/priority", response_model=AnnotationResponse)
def set_priority(
    executive_id: int,
    event_id: str,
    priority: str,
    db: Session = Depends(get_db)
):
    """Set priority for a meeting."""
    service = AnnotationService(db)
    annotation = service.set_priority(executive_id, event_id, priority)
    return annotation


# ============================================================================
# RELATIONSHIP ENDPOINTS
# ============================================================================

@router.post("/executives/{executive_id}/relationships", response_model=RelationshipResponse, status_code=201)
def create_relationship(
    executive_id: int,
    relationship: RelationshipCreate,
    db: Session = Depends(get_db)
):
    """Create or update relationship record."""
    service = RelationshipService(db)

    created = service.create_or_update_relationship(
        executive_id=executive_id,
        person_email=relationship.person_email,
        person_name=relationship.person_name,
        person_company=relationship.person_company,
        relationship_strength=relationship.relationship_strength.value,
        relationship_status=relationship.relationship_status.value if relationship.relationship_status else None,
        relationship_notes=relationship.relationship_notes
    )

    return created


@router.get("/executives/{executive_id}/relationships", response_model=List[RelationshipResponse])
def list_relationships(
    executive_id: int,
    relationship_strength: Optional[str] = None,
    relationship_status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all relationships for an executive."""
    service = RelationshipService(db)
    return service.list_relationships(
        executive_id=executive_id,
        relationship_strength=relationship_strength,
        relationship_status=relationship_status
    )


@router.get("/executives/{executive_id}/relationships/{person_email}", response_model=RelationshipResponse)
def get_relationship(
    executive_id: int,
    person_email: str,
    db: Session = Depends(get_db)
):
    """Get relationship record for a specific person."""
    service = RelationshipService(db)
    relationship = service.get_relationship(executive_id, person_email)

    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")

    return relationship


@router.put("/executives/{executive_id}/relationships/{person_email}", response_model=RelationshipResponse)
def update_relationship(
    executive_id: int,
    person_email: str,
    updates: RelationshipUpdate,
    db: Session = Depends(get_db)
):
    """Update relationship record."""
    service = RelationshipService(db)

    relationship = service.get_relationship(executive_id, person_email)
    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")

    update_dict = updates.dict(exclude_unset=True)
    # Convert enums to strings
    if 'relationship_strength' in update_dict:
        update_dict['relationship_strength'] = update_dict['relationship_strength'].value
    if 'relationship_status' in update_dict and update_dict['relationship_status']:
        update_dict['relationship_status'] = update_dict['relationship_status'].value

    updated = service.update_relationship(relationship.id, **update_dict)
    return updated


@router.delete("/executives/{executive_id}/relationships/{person_email}", status_code=204)
def delete_relationship(
    executive_id: int,
    person_email: str,
    db: Session = Depends(get_db)
):
    """Delete relationship record."""
    service = RelationshipService(db)
    relationship = service.get_relationship(executive_id, person_email)

    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")

    service.delete_relationship(relationship.id)


@router.get("/executives/{executive_id}/relationships/follow-ups", response_model=List[RelationshipResponse])
def get_follow_ups(
    executive_id: int,
    before_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """Get relationships needing follow-up."""
    service = RelationshipService(db)
    return service.get_relationships_needing_follow_up(
        executive_id=executive_id,
        before_date=before_date
    )


@router.post("/executives/{executive_id}/relationships/{person_email}/follow-up", response_model=RelationshipResponse)
def record_follow_up(
    executive_id: int,
    person_email: str,
    follow_up_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """Record that a follow-up occurred."""
    service = RelationshipService(db)
    relationship = service.record_follow_up(
        executive_id=executive_id,
        person_email=person_email,
        follow_up_date=follow_up_date
    )

    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")

    return relationship
