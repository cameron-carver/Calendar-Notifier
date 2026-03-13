"""
Metrics tracking and aggregation service for usage dashboard.
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.brief import BriefMetrics, Brief
from app.schemas.brief import MeetingEvent


class MetricsService:
    """Service for tracking and aggregating brief generation metrics."""

    def track_brief_generation(
        self,
        brief_id: int,
        events: List[MeetingEvent],
        generation_time: float,
        api_stats: Dict[str, int],
        db: Session
    ) -> BriefMetrics:
        """
        Record metrics for a brief generation.

        Args:
            brief_id: ID of the generated brief
            events: List of meeting events processed
            generation_time: Time taken to generate brief (seconds)
            api_stats: Dictionary with API usage counts
                - 'affinity': Number of Affinity API calls
                - 'openai_tokens': OpenAI tokens used
                - 'news': Number of News API calls
            db: Database session

        Returns:
            Created BriefMetrics record
        """
        # Count enriched meetings (those with at least one attendee with company data)
        meetings_enriched = sum(
            1 for event in events
            if event.attendees and any(
                attendee.company or attendee.company_description
                for attendee in event.attendees
            )
        )

        # Count meetings with AI prep
        meetings_with_ai_prep = sum(
            1 for event in events
            if event.ai_summary
        )

        # Count successful enrichments
        linkedin_found = sum(
            1 for event in events
            for attendee in (event.attendees or [])
            if attendee.linkedin_url
        )

        news_articles_found = sum(
            len(attendee.news_articles or [])
            for event in events
            for attendee in (event.attendees or [])
        )

        company_data_found = sum(
            1 for event in events
            for attendee in (event.attendees or [])
            if attendee.company_description
        )

        # Create metrics record
        metrics = BriefMetrics(
            brief_id=brief_id,
            meetings_processed=len(events),
            meetings_enriched=meetings_enriched,
            meetings_with_ai_prep=meetings_with_ai_prep,
            affinity_api_calls=api_stats.get('affinity', 0),
            openai_tokens_used=api_stats.get('openai_tokens', 0),
            news_api_calls=api_stats.get('news', 0),
            linkedin_found=linkedin_found,
            news_articles_found=news_articles_found,
            company_data_found=company_data_found,
            generation_time_seconds=generation_time
        )

        db.add(metrics)
        db.commit()
        db.refresh(metrics)

        return metrics

    def get_aggregated_metrics(self, days: int, db: Session) -> Dict[str, Any]:
        """
        Get aggregated metrics for dashboard.

        Args:
            days: Number of days to analyze
            db: Database session

        Returns:
            Dictionary with aggregated statistics
        """
        cutoff = datetime.now() - timedelta(days=days)

        # Query all metrics within the time period
        metrics = db.query(BriefMetrics).join(
            Brief, BriefMetrics.brief_id == Brief.id
        ).filter(
            Brief.created_at >= cutoff
        ).all()

        if not metrics:
            return {
                "total_briefs": 0,
                "total_meetings": 0,
                "total_tokens": 0,
                "avg_generation_time": 0.0,
                "enrichment_rate": 0.0,
                "meetings_with_ai_prep": 0,
                "affinity_api_calls": 0,
                "news_api_calls": 0,
                "linkedin_found": 0,
                "news_articles_found": 0,
                "company_data_found": 0,
                "days_analyzed": days
            }

        # Calculate aggregates
        total_meetings = sum(m.meetings_processed for m in metrics)
        total_enriched = sum(m.meetings_enriched for m in metrics)

        enrichment_rate = (
            total_enriched / total_meetings
            if total_meetings > 0
            else 0.0
        )

        # Average generation time (only for non-null values)
        generation_times = [
            m.generation_time_seconds
            for m in metrics
            if m.generation_time_seconds is not None
        ]
        avg_generation_time = (
            sum(generation_times) / len(generation_times)
            if generation_times
            else 0.0
        )

        return {
            "total_briefs": len(metrics),
            "total_meetings": total_meetings,
            "total_tokens": sum(m.openai_tokens_used for m in metrics),
            "avg_generation_time": round(avg_generation_time, 2),
            "enrichment_rate": round(enrichment_rate, 2),
            "meetings_with_ai_prep": sum(m.meetings_with_ai_prep for m in metrics),
            "affinity_api_calls": sum(m.affinity_api_calls for m in metrics),
            "news_api_calls": sum(m.news_api_calls for m in metrics),
            "linkedin_found": sum(m.linkedin_found for m in metrics),
            "news_articles_found": sum(m.news_articles_found for m in metrics),
            "company_data_found": sum(m.company_data_found for m in metrics),
            "days_analyzed": days
        }

    def get_most_met_people(
        self,
        days: int,
        limit: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get most frequently met people in the time period.

        Args:
            days: Number of days to analyze
            limit: Maximum number of results to return
            db: Database session

        Returns:
            List of dictionaries with person info and meeting count
        """
        # This would require storing attendee details in a separate table
        # For now, return placeholder
        # TODO: Implement attendee tracking table for this feature
        return []

    def get_meeting_trends(
        self,
        days: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get meeting counts per day for trend chart.

        Args:
            days: Number of days to analyze
            db: Database session

        Returns:
            List of dictionaries with date and meeting count
        """
        cutoff = datetime.now() - timedelta(days=days)

        # Query briefs with metrics grouped by date
        results = db.query(
            func.date(Brief.date).label('date'),
            func.sum(BriefMetrics.meetings_processed).label('count')
        ).join(
            BriefMetrics, Brief.id == BriefMetrics.brief_id
        ).filter(
            Brief.created_at >= cutoff
        ).group_by(
            func.date(Brief.date)
        ).order_by(
            func.date(Brief.date)
        ).all()

        return [
            {
                "date": row.date.isoformat() if row.date else None,
                "count": row.count or 0
            }
            for row in results
        ]

    def get_persona_distribution(
        self,
        days: int,
        db: Session
    ) -> Dict[str, int]:
        """
        Get distribution of attendee personas.

        Args:
            days: Number of days to analyze
            db: Database session

        Returns:
            Dictionary mapping persona type to count
        """
        # This would require storing attendee persona data
        # For now, return placeholder
        # TODO: Implement attendee tracking for persona distribution
        return {
            "founder": 0,
            "coinvestor": 0,
            "lp": 0,
            "corporate": 0,
            "service_provider": 0,
            "internal": 0,
            "unknown": 0
        }
