# Deployment Guide - Morning Brief

This guide covers deploying the Morning Brief tool to various environments.

## Local Development Setup

### Prerequisites

1. **Python 3.8+**
2. **PostgreSQL** database
3. **Redis** for task queuing
4. **API Keys** for all services

### Quick Start

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd Calendar\ Notifier
   python setup.py
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp env.example .env
   # Edit .env with your API keys and configuration
   ```

4. **Setup database**:
   ```bash
   # Create PostgreSQL database
   createdb morning_brief
   
   # Run migrations
   alembic upgrade head
   ```

5. **Start services**:
   ```bash
   # Terminal 1: Start Redis
   redis-server
   
   # Terminal 2: Start Celery worker
   celery -A app.core.celery_app worker --loglevel=info
   
   # Terminal 3: Start FastAPI server
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

6. **Test the setup**:
   ```bash
   python test_brief.py
   ```

## API Key Setup

### Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Calendar API
4. Create OAuth 2.0 credentials
5. Download credentials JSON file
6. Set `GOOGLE_CALENDAR_CREDENTIALS_FILE` in `.env`

### Affinity API

1. Log into your Affinity account
2. Go to Settings → API Keys
3. Generate a new API key
4. Set `AFFINITY_API_KEY` in `.env`

### OpenAI API

1. Sign up at [OpenAI](https://platform.openai.com/)
2. Create an API key
3. Set `OPENAI_API_KEY` in `.env`

### News API

1. Sign up at [NewsAPI](https://newsapi.org/)
2. Get your API key
3. Set `NEWS_API_KEY` in `.env`

### Gmail API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail API
3. Create OAuth 2.0 credentials for Gmail
4. Download credentials JSON file
5. Set `GMAIL_CREDENTIALS_FILE` in `.env`

## Production Deployment

### Docker Deployment

1. **Create Dockerfile**:
   ```dockerfile
   FROM python:3.9-slim
   
   WORKDIR /app
   
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   
   COPY . .
   
   EXPOSE 8000
   
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

2. **Create docker-compose.yml**:
   ```yaml
   version: '3.8'
   
   services:
     app:
       build: .
       ports:
         - "8000:8000"
       environment:
         - DATABASE_URL=postgresql://user:password@db:5432/morning_brief
         - REDIS_URL=redis://redis:6379
       depends_on:
         - db
         - redis
       volumes:
         - ./credentials:/app/credentials:ro
   
     db:
       image: postgres:13
       environment:
         - POSTGRES_DB=morning_brief
         - POSTGRES_USER=user
         - POSTGRES_PASSWORD=password
       volumes:
         - postgres_data:/var/lib/postgresql/data
   
     redis:
       image: redis:6-alpine
   
     celery:
       build: .
       command: celery -A app.core.celery_app worker --loglevel=info
       environment:
         - DATABASE_URL=postgresql://user:password@db:5432/morning_brief
         - REDIS_URL=redis://redis:6379
       depends_on:
         - db
         - redis
       volumes:
         - ./credentials:/app/credentials:ro
   
   volumes:
     postgres_data:
   ```

3. **Deploy**:
   ```bash
   docker-compose up -d
   ```

### Cloud Deployment

#### AWS Deployment

1. **EC2 Setup**:
   ```bash
   # Launch EC2 instance
   # Install Docker and Docker Compose
   sudo yum update -y
   sudo yum install -y docker
   sudo service docker start
   sudo usermod -a -G docker ec2-user
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

2. **RDS Setup**:
   - Create PostgreSQL RDS instance
   - Update `DATABASE_URL` in environment

3. **ElastiCache Setup**:
   - Create Redis ElastiCache cluster
   - Update `REDIS_URL` in environment

4. **Deploy**:
   ```bash
   git clone <repository-url>
   cd Calendar\ Notifier
   # Configure .env with production values
   docker-compose up -d
   ```

#### Google Cloud Deployment

1. **Cloud Run Setup**:
   ```bash
   # Build and deploy to Cloud Run
   gcloud builds submit --tag gcr.io/PROJECT_ID/morning-brief
   gcloud run deploy morning-brief --image gcr.io/PROJECT_ID/morning-brief --platform managed
   ```

2. **Cloud SQL Setup**:
   - Create Cloud SQL PostgreSQL instance
   - Update `DATABASE_URL`

3. **Cloud Memorystore Setup**:
   - Create Redis instance
   - Update `REDIS_URL`

#### Heroku Deployment

1. **Create Heroku app**:
   ```bash
   heroku create morning-brief-app
   ```

2. **Add add-ons**:
   ```bash
   heroku addons:create heroku-postgresql:hobby-dev
   heroku addons:create heroku-redis:hobby-dev
   ```

3. **Configure environment**:
   ```bash
   heroku config:set DATABASE_URL=$(heroku config:get DATABASE_URL)
   heroku config:set REDIS_URL=$(heroku config:get REDIS_TLS_URL)
   # Set other environment variables
   ```

4. **Deploy**:
   ```bash
   git push heroku main
   ```

## Automated Scheduling

### Cron Job Setup

1. **Create cron job**:
   ```bash
   # Edit crontab
   crontab -e
   
   # Add daily job at 8:00 AM
   0 8 * * * cd /path/to/morning-brief && python -c "from app.tasks.brief_tasks import generate_and_send_morning_brief; generate_and_send_morning_brief.delay()"
   ```

### Cloud Scheduler (AWS)

1. **Create CloudWatch Event**:
   ```json
   {
     "schedule": "cron(0 8 * * ? *)",
     "targets": [
       {
         "id": "morning-brief",
         "arn": "arn:aws:lambda:region:account:function:morning-brief-lambda",
         "input": "{}"
       }
     ]
   }
   ```

### Cloud Scheduler (Google Cloud)

1. **Create Cloud Scheduler job**:
   ```bash
   gcloud scheduler jobs create http morning-brief \
     --schedule="0 8 * * *" \
     --uri="https://your-app-url/briefs/generate-and-send" \
     --http-method=POST
   ```

## Monitoring and Logging

### Health Checks

- **API Health**: `GET /health`
- **Database Health**: Check connection pool
- **Redis Health**: Check Celery worker status

### Logging

1. **Configure logging**:
   ```python
   import logging
   
   logging.basicConfig(
       level=logging.INFO,
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       handlers=[
           logging.FileHandler('morning-brief.log'),
           logging.StreamHandler()
       ]
   )
   ```

2. **Monitor logs**:
   ```bash
   # Follow application logs
   tail -f morning-brief.log
   
   # Follow Celery logs
   tail -f celery.log
   ```

### Error Handling

1. **Set up error monitoring** (Sentry):
   ```python
   import sentry_sdk
   from sentry_sdk.integrations.fastapi import FastApiIntegration
   
   sentry_sdk.init(
       dsn="your-sentry-dsn",
       integrations=[FastApiIntegration()]
   )
   ```

## Security Considerations

1. **Environment Variables**: Never commit API keys to version control
2. **Database Security**: Use strong passwords and SSL connections
3. **API Security**: Implement rate limiting and authentication
4. **Network Security**: Use VPC and security groups in cloud deployments
5. **Credential Rotation**: Regularly rotate API keys

## Backup and Recovery

1. **Database Backups**:
   ```bash
   # PostgreSQL backup
   pg_dump morning_brief > backup_$(date +%Y%m%d).sql
   
   # Restore
   psql morning_brief < backup_20231201.sql
   ```

2. **Configuration Backups**:
   - Backup `.env` file
   - Backup credential files
   - Backup database migrations

## Troubleshooting

### Common Issues

1. **Calendar API Errors**:
   - Check OAuth credentials
   - Verify calendar permissions
   - Check API quotas

2. **Database Connection Issues**:
   - Verify connection string
   - Check network connectivity
   - Verify database exists

3. **Celery Worker Issues**:
   - Check Redis connection
   - Verify task imports
   - Check worker logs

4. **Email Delivery Issues**:
   - Verify Gmail API credentials
   - Check email quotas
   - Verify recipient email

### Debug Mode

Enable debug mode for development:
```bash
export ENVIRONMENT=development
export LOG_LEVEL=DEBUG
```

## Performance Optimization

1. **Database Optimization**:
   - Add indexes for frequently queried fields
   - Use connection pooling
   - Implement caching

2. **API Optimization**:
   - Implement request caching
   - Use async operations
   - Optimize database queries

3. **Task Optimization**:
   - Use task routing
   - Implement retry logic
   - Monitor task performance 