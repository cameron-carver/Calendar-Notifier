"""
Settings inheritance resolver for Calendar Notifier.

Resolves effective settings with cascade:
.env (global defaults) → UserSettings (database) → FilterPreset → request overrides
"""
from typing import Optional, Any, Dict
from datetime import datetime
from app.core.config import settings
from app.models.brief import UserSettings, FilterPreset


class SettingsResolver:
    """
    Resolves effective settings with inheritance hierarchy.

    Priority (lowest to highest):
    1. Global defaults from .env file (via app.core.config.settings)
    2. User-specific settings from database (UserSettings table)
    3. Active filter preset (FilterPreset table)
    4. Request-time overrides (temporary, for previews)
    """

    def __init__(
        self,
        user_settings: Optional[UserSettings] = None,
        active_preset: Optional[FilterPreset] = None,
        request_overrides: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize settings resolver.

        Args:
            user_settings: User's database settings (or None for defaults)
            active_preset: Active filter preset (or None)
            request_overrides: Temporary overrides for preview (or None)
        """
        self.global_settings = settings  # From .env
        self.user_settings = user_settings
        self.active_preset = active_preset
        self.request_overrides = request_overrides or {}

    def get_delivery_time(self, day_of_week: Optional[str] = None) -> str:
        """
        Get delivery time for specific day or default.

        Args:
            day_of_week: Day name (lowercase: "monday", "tuesday", etc.) or None for default

        Returns:
            Time string in HH:MM format
        """
        # Check request overrides first
        if "delivery_time" in self.request_overrides:
            return self.request_overrides["delivery_time"]

        # Check user settings for day-specific schedule
        if self.user_settings and self.user_settings.delivery_schedule:
            schedule = self.user_settings.delivery_schedule
            if day_of_week and day_of_week in schedule:
                return schedule[day_of_week]
            # Fall back to "default" key in schedule
            if "default" in schedule:
                return schedule["default"]

        # Fall back to user's delivery_time column (backward compatibility)
        if self.user_settings and self.user_settings.delivery_time:
            return self.user_settings.delivery_time

        # Fall back to global default
        return self.global_settings.default_delivery_time

    def get_current_delivery_time(self) -> str:
        """Get delivery time for today's day of week."""
        day_name = datetime.now().strftime("%A").lower()
        return self.get_delivery_time(day_name)

    def get_content_depth(self) -> str:
        """
        Get content depth preference.

        Returns:
            One of: "quick", "standard", "detailed"
        """
        # Check request overrides
        if "content_depth" in self.request_overrides:
            return self.request_overrides["content_depth"]

        # Check user settings
        if self.user_settings and self.user_settings.content_depth:
            return self.user_settings.content_depth

        # Default to standard
        return "standard"

    def get_time_window_hours(self) -> int:
        """
        Get meeting time window in hours.

        Returns:
            Number of hours (0 = all day)
        """
        # Check request overrides
        if "time_window_hours" in self.request_overrides:
            return self.request_overrides["time_window_hours"]

        # Check user settings
        if self.user_settings and self.user_settings.time_window_hours is not None:
            return self.user_settings.time_window_hours

        # Fall back to global setting
        return self.global_settings.time_window_hours

    def get_feature_flag(self, flag_name: str) -> bool:
        """
        Get effective feature flag value with inheritance.

        Args:
            flag_name: Name of the flag (e.g., "enable_ai_prep")

        Returns:
            Boolean value for the flag
        """
        # Check request overrides
        if flag_name in self.request_overrides:
            return bool(self.request_overrides[flag_name])

        # Check user settings (None = not set, use global)
        if self.user_settings:
            user_value = getattr(self.user_settings, flag_name, None)
            if user_value is not None:
                return user_value

        # Fall back to global setting (with sensible defaults if not defined)
        return getattr(self.global_settings, flag_name, True)

    def get_filter_config(self) -> Dict[str, Any]:
        """
        Get merged filter configuration.

        Returns:
            Dictionary with all filter settings
        """
        config = {
            "require_non_owner": self.get_feature_flag("filter_require_non_owner"),
            "external_only": self.get_feature_flag("filter_external_only"),
            "exclude_recurring": self.get_feature_flag("filter_exclude_recurring"),
            "time_window_hours": self.get_time_window_hours()
        }

        # Apply active preset filters if present
        if self.active_preset and self.active_preset.filters:
            config.update(self.active_preset.filters)

        # Apply request overrides
        for key in ["require_non_owner", "external_only", "exclude_recurring"]:
            if key in self.request_overrides:
                config[key] = self.request_overrides[key]

        return config

    def get_max_news_articles(self) -> int:
        """Get maximum news articles per person."""
        # Check request overrides
        if "max_news_articles" in self.request_overrides:
            return self.request_overrides["max_news_articles"]

        # Check user settings
        if self.user_settings and self.user_settings.max_news_articles is not None:
            return self.user_settings.max_news_articles

        # Fall back to global setting
        return self.global_settings.max_news_articles_per_person

    def should_enable_ai_prep(self) -> bool:
        """Check if AI prep should be generated."""
        return self.get_feature_flag("enable_ai_prep")

    def should_enable_news(self) -> bool:
        """Check if news enrichment should run."""
        return self.get_feature_flag("enable_news")

    def should_enable_meeting_history(self) -> bool:
        """Check if meeting history should be included."""
        return self.get_feature_flag("enable_meeting_history")

    def should_enable_affinity_data(self) -> bool:
        """Check if Affinity CRM data should be included."""
        return self.get_feature_flag("enable_affinity_data")

    def should_enable_web_enrichment(self) -> bool:
        """Check if web enrichment should run."""
        return self.get_feature_flag("enable_web_enrichment")

    def get_all_settings(self) -> Dict[str, Any]:
        """
        Get all resolved settings as a dictionary.

        Useful for API responses showing current effective configuration.

        Returns:
            Dictionary with all resolved settings
        """
        return {
            "delivery_time": self.get_current_delivery_time(),
            "delivery_schedule": self.user_settings.delivery_schedule if self.user_settings else None,
            "timezone": self.user_settings.timezone if self.user_settings else self.global_settings.timezone,
            "content_depth": self.get_content_depth(),
            "time_window_hours": self.get_time_window_hours(),
            "enable_ai_prep": self.should_enable_ai_prep(),
            "enable_news": self.should_enable_news(),
            "enable_meeting_history": self.should_enable_meeting_history(),
            "enable_affinity_data": self.should_enable_affinity_data(),
            "enable_web_enrichment": self.should_enable_web_enrichment(),
            "filter_require_non_owner": self.get_feature_flag("filter_require_non_owner"),
            "filter_external_only": self.get_feature_flag("filter_external_only"),
            "filter_exclude_recurring": self.get_feature_flag("filter_exclude_recurring"),
            "max_news_articles": self.get_max_news_articles(),
            "talking_points_enabled": self.get_feature_flag("talking_points_enabled") if self.user_settings else self.global_settings.enable_talking_points
        }
