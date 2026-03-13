import asyncio
from celery import shared_task
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.brief_service import BriefService
from app.models.brief import Brief, UserSettings
from app.core.config import settings as app_settings


def _run_async(coro):
    """Run an async coroutine in a sync Celery task."""
    return asyncio.run(coro)


@shared_task
def generate_and_send_morning_brief():
    """Celery task to generate and send the morning brief."""
    return _run_async(_generate_and_send())


async def _generate_and_send():
    db = SessionLocal()
    try:
        # Pass DB session so BriefService can access journal + todo data
        brief_service = BriefService(db=db)

        # Get user settings — fall back to owner email from .env
        user_settings = brief_service.get_user_settings(db)
        if user_settings and not user_settings.is_active:
            print("User settings found but not active — skipping")
            return False

        recipient = (
            user_settings.email_address
            if user_settings
            else app_settings.owner_email
        )
        if not recipient:
            print("No recipient email configured — cannot send brief")
            return False

        # Generate brief for today (now includes news, todos, time blocks, journal)
        brief_response = await brief_service.generate_daily_brief()

        has_content = (
            brief_response.events_summary
            or brief_response.industry_news
            or brief_response.weekly_todos
            or brief_response.time_blocks
        )
        if not has_content:
            print("No meetings or newsletter content today — skipping email send")
            return True

        # Save to database
        brief = brief_service.save_brief_to_database(brief_response, db)

        # Send email (pass full brief_response for newsletter sections)
        success = await brief_service.send_morning_brief(
            recipient,
            brief_response.content,
            enriched_events=brief_response.events_summary,
            brief_response=brief_response,
        )

        if success:
            brief.is_sent = True
            brief.sent_at = datetime.now()
            db.commit()
            print(f"Morning brief sent successfully to {recipient}")
        else:
            print("Failed to send morning brief")

        return success

    except Exception as e:
        print(f"Error in generate_and_send_morning_brief task: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


@shared_task
def generate_brief_for_date(target_date_str: str):
    """Celery task to generate a brief for a specific date."""
    return _run_async(_generate_for_date(target_date_str))


async def _generate_for_date(target_date_str: str):
    db = SessionLocal()
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        brief_service = BriefService()

        brief_response = await brief_service.generate_daily_brief(target_date)
        brief = brief_service.save_brief_to_database(brief_response, db)

        print(f"Brief generated for {target_date_str}")
        return True

    except Exception as e:
        print(f"Error in generate_brief_for_date task: {e}")
        return False
    finally:
        db.close()


@shared_task
def send_brief_email(brief_id: int, user_email: str):
    """Celery task to send a specific brief via email."""
    return _run_async(_send_email(brief_id, user_email))


async def _send_email(brief_id: int, user_email: str):
    db = SessionLocal()
    try:
        brief_service = BriefService()

        brief = db.query(Brief).filter(Brief.id == brief_id).first()
        if not brief:
            print(f"Brief with ID {brief_id} not found")
            return False

        success = await brief_service.send_morning_brief(user_email, brief.content)

        if success:
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


@shared_task
def send_journal_prompt():
    """Celery task to send the 7pm evening journal prompt."""
    return _run_async(_send_journal())


async def _send_journal():
    db = SessionLocal()
    try:
        from app.services.journal_service import JournalService
        from app.services.email.gmail_service import GmailService
        from app.services.ai.summarization_service import SummarizationService

        gmail = GmailService()
        ai = SummarizationService()
        journal_service = JournalService(db=db, gmail=gmail, ai=ai)

        # Get today's events for the recap
        brief_service = BriefService()
        events = brief_service.calendar_service.get_daily_events(date.today())

        # Get recipient
        user_settings = brief_service.get_user_settings(db)
        recipient = (
            user_settings.email_address
            if user_settings
            else app_settings.owner_email
        )

        if not recipient:
            print("No recipient email configured — cannot send journal prompt")
            return False

        # Send prompt
        entry = await journal_service.send_evening_prompt(recipient, events or [])
        print(f"Journal prompt sent to {recipient}, entry id={entry.id}")
        return True

    except Exception as e:
        print(f"Error in send_journal_prompt task: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


@shared_task
def refresh_tokens() -> bool:
    """Weekly token refresh task to validate scopes and refresh Google tokens."""
    try:
        from tools.token_refresh import main as token_main
        exit_code = token_main()
        print(f"Token refresh completed with code {exit_code}")
        return exit_code == 0
    except Exception as e:
        print(f"Error in token refresh task: {e}")
        return False
