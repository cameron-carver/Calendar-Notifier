#!/usr/bin/env python3
"""
Setup script for Morning Brief - Calendar Notifier
"""

import os
import sys
import subprocess
from pathlib import Path


def run_command(command, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return False


def create_env_file():
    """Create .env file from template."""
    env_example = Path("env.example")
    env_file = Path(".env")
    
    if env_file.exists():
        print("⚠️  .env file already exists, skipping creation")
        return True
    
    if not env_example.exists():
        print("❌ env.example file not found")
        return False
    
    print("📝 Creating .env file from template...")
    try:
        with open(env_example, 'r') as f:
            content = f.read()
        
        with open(env_file, 'w') as f:
            f.write(content)
        
        print("✅ .env file created successfully")
        print("⚠️  Please edit .env file with your API keys and configuration")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False


def check_dependencies():
    """Check if required dependencies are installed."""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "psycopg2-binary",
        "alembic",
        "celery",
        "redis",
        "openai",
        "newsapi-python",
        "google-auth",
        "google-api-python-client",
        "httpx"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print("Please install missing packages with: pip install -r requirements.txt")
        return False
    
    print("✅ All required packages are installed")
    return True


def setup_database():
    """Set up database and run migrations."""
    print("🗄️  Setting up database...")
    
    # Check if database URL is configured
    if not os.getenv("DATABASE_URL"):
        print("⚠️  DATABASE_URL not set in .env file")
        print("Please configure your database connection in .env file")
        return False
    
    # Run database migrations
    if not run_command("alembic upgrade head", "Running database migrations"):
        return False
    
    print("✅ Database setup completed")
    return True


def main():
    """Main setup function."""
    print("🚀 Setting up Morning Brief - Calendar Notifier")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Create .env file
    if not create_env_file():
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Setup database
    if not setup_database():
        print("⚠️  Database setup incomplete. Please configure your database and run migrations manually.")
    
    print("\n" + "=" * 50)
    print("🎉 Setup completed!")
    print("\nNext steps:")
    print("1. Edit .env file with your API keys:")
    print("   - Google Calendar API credentials")
    print("   - Affinity API key")
    print("   - OpenAI API key")
    print("   - News API key")
    print("   - Gmail API credentials")
    print("   - Database connection string")
    print("   - Redis connection string")
    print("\n2. Start the services:")
    print("   - Redis: redis-server")
    print("   - Celery: celery -A app.core.celery_app worker --loglevel=info")
    print("   - FastAPI: uvicorn app.main:app --reload")
    print("\n3. Access the API documentation at: http://localhost:8000/docs")
    print("\n4. Configure your user settings via the API")
    print("\n5. Set up automated scheduling (cron job or cloud scheduler)")


if __name__ == "__main__":
    main() 