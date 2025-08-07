from celery import shared_task
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.brief_service import BriefService
from app.models.brief import Brief, UserSettings


@shared_task
async def generate_and_send_morning_brief():
    """Celery task to generate and send the morning brief."""
    db = SessionLocal()
    try:
        brief_service = BriefService()
        
        # Get user settings
        user_settings = brief_service.get_user_settings(db)
        if not user_settings or not user_settings.is_active:
            print("No active user settings found")
            return False
        
        # Generate brief
        brief_response = await brief_service.generate_daily_brief()
        
        # Save to database
        brief = brief_service.save_brief_to_database(brief_response, db)
        
        # Send email
        success = await brief_service.send_morning_brief(
            user_settings.email_address, 
            brief_response.content
        )
        
        if success:
            # Update brief as sent
            brief.is_sent = True
            brief.sent_at = datetime.now()
            db.commit()
            print(f"Morning brief sent successfully to {user_settings.email_address}")
        else:
            print("Failed to send morning brief")
        
        return success
        
    except Exception as e:
        print(f"Error in generate_and_send_morning_brief task: {e}")
        return False
    finally:
        db.close()


@shared_task
async def generate_brief_for_date(target_date_str: str):
    """Celery task to generate a brief for a specific date."""
    db = SessionLocal()
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        brief_service = BriefService()
        
        # Generate brief
        brief_response = await brief_service.generate_daily_brief(target_date)
        
        # Save to database
        brief = brief_service.save_brief_to_database(brief_response, db)
        
        print(f"Brief generated for {target_date_str}")
        return True
        
    except Exception as e:
        print(f"Error in generate_brief_for_date task: {e}")
        return False
    finally:
        db.close()


@shared_task
async def send_brief_email(brief_id: int, user_email: str):
    """Celery task to send a specific brief via email."""
    db = SessionLocal()
    try:
        brief_service = BriefService()
        
        # Get brief from database
        brief = db.query(Brief).filter(Brief.id == brief_id).first()
        if not brief:
            print(f"Brief with ID {brief_id} not found")
            return False
        
        # Send email
        success = await brief_service.send_morning_brief(user_email, brief.content)
        
        if success:
            # Update brief as sent
            brief.is_sent = True
            brief.sent_at = datetime.now()
            db.commit()
            print(f"Brief {brief_id} sent successfully to {user_email}")
        else:
            print(f"Failed to send brief {brief_id}")
        
        return success
        
    except Exception as e:
        print(f"Error in send_brief_email task: {e}")
        return False
    finally:
        db.close()


@shared_task
def cleanup_old_briefs(days_to_keep: int = 30):
    """Celery task to cleanup old briefs from the database."""
    db = SessionLocal()
    try:
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        # Delete old briefs
        deleted_count = db.query(Brief).filter(
            Brief.created_at < cutoff_date
        ).delete()
        
        db.commit()
        print(f"Cleaned up {deleted_count} old briefs")
        return deleted_count
        
    except Exception as e:
        print(f"Error in cleanup_old_briefs task: {e}")
        return 0
    finally:
        db.close() 