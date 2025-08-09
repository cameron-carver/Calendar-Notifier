# Morning Brief - Calendar Notifier

An intelligent morning brief tool that automatically sends personalized meeting summaries based on your daily calendar events, enriched with contact information and recent news.

## Features

- **Automated Calendar Integration**: Fetches daily events from Google Calendar
- **Contact Enrichment**: Uses Affinity API to get detailed person/company information
- **News Aggregation**: Includes recent news about meeting attendees and their companies
- **AI-Powered Summaries**: Generates intelligent briefs with context and talking points
- **Customizable Delivery**: Configurable delivery time (default: 8:00 AM local time)
- **Email Integration**: Sends briefs via Gmail

## Architecture

```
Google Calendar → Extract attendees → Affinity API → Enrich with company/person data → 
News APIs → Generate brief → Send email
```

## Setup

### Prerequisites

- Python 3.8+
- Google Calendar API credentials
- Affinity API key
- OpenAI API key (for AI summarization)
- News API key
- Gmail API credentials
- PostgreSQL database
- Redis (for task scheduling)

### Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. Initialize the database:
   ```bash
   alembic upgrade head
   ```

5. Start the services:
   ```bash
   # Start Redis
   redis-server

   # Start Celery worker
   celery -A app.celery worker --loglevel=info

   # Start the FastAPI server
   uvicorn app.main:app --reload
   ```

## Configuration

Create a `.env` file with the following variables:

```env
# API Keys
GOOGLE_CALENDAR_CREDENTIALS_FILE=path/to/credentials.json
AFFINITY_API_KEY=your_affinity_api_key
OPENAI_API_KEY=your_openai_api_key
NEWS_API_KEY=your_news_api_key
GMAIL_CREDENTIALS_FILE=path/to/gmail_credentials.json

# Database
DATABASE_URL=postgresql://user:password@localhost/morning_brief

# Redis
REDIS_URL=redis://localhost:6379

# App Settings
DEFAULT_DELIVERY_TIME=08:00
TIMEZONE=America/New_York
```

## Usage

### Manual Brief Generation

```python
from app.services.brief_service import BriefService

brief_service = BriefService()
brief = await brief_service.generate_daily_brief()
```

### Automated Scheduling

- Celery Beat triggers `generate_and_send_morning_brief` at `DEFAULT_DELIVERY_TIME` (local timezone).
- Run locally:
  ```bash
  redis-server &
  celery -A app.core.celery_app.celery_app worker -l info &
  celery -A app.core.celery_app.celery_app beat -l info
  ```

### API Endpoints

- `GET /health` - Health check
- `POST /briefs/generate` - Manually generate a brief
- `GET /briefs/history` - View brief history
- `PUT /settings` - Update user preferences

## Project Structure

```
app/
├── api/                 # FastAPI routes
├── core/               # Core configuration
├── models/             # Database models
├── services/           # Business logic
│   ├── calendar/       # Google Calendar integration
│   ├── affinity/       # Affinity API integration
│   ├── news/          # News aggregation
│   ├── ai/            # AI summarization
│   └── email/         # Email delivery
├── tasks/             # Celery tasks
└── utils/             # Utility functions
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
flake8 .
```

## License

MIT License 