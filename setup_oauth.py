#!/usr/bin/env python3
"""
Google OAuth Setup Helper Script
This script helps you set up Google OAuth credentials for Calendar and Gmail access.
"""

import os
import json
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# OAuth scopes needed for the application
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send'
]

def setup_oauth():
    """Set up OAuth credentials for Google Calendar and Gmail."""
    creds = None
    
    # Check if token file exists
    token_file = 'token.json'
    if os.path.exists(token_file):
        print(f"✅ Found existing token file: {token_file}")
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    # If no valid credentials available, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("🔐 Setting up new OAuth credentials...")
            print("\n📋 Instructions:")
            print("1. Go to https://console.cloud.google.com/")
            print("2. Create a new project or select existing one")
            print("3. Enable these APIs:")
            print("   - Google Calendar API")
            print("   - Gmail API")
            print("4. Go to 'Credentials' → 'Create Credentials' → 'OAuth 2.0 Client IDs'")
            print("5. Choose 'Desktop application'")
            print("6. Download the JSON file")
            print("7. Place it in this directory as 'client_secret.json'")
            print("\n⏳ Waiting for client_secret.json...")
            
            # Wait for user to place the file
            while not os.path.exists('client_secret.json'):
                input("Press Enter when you've placed client_secret.json in this directory...")
            
            print("✅ Found client_secret.json!")
            
            # Run the OAuth flow
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
        print(f"✅ Credentials saved to {token_file}")
    
    print("🎉 OAuth setup complete!")
    return creds

def create_credentials_file():
    """Create the credentials file in the format expected by the app."""
    if not os.path.exists('token.json'):
        print("❌ No token.json found. Please run setup_oauth() first.")
        return
    
    # Read the token file
    with open('token.json', 'r') as f:
        token_data = json.load(f)
    
    # Create the credentials file with the required format
    credentials_data = {
        "client_id": token_data.get("client_id"),
        "client_secret": token_data.get("client_secret"),
        "refresh_token": token_data.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": SCOPES
    }
    
    # Save to the file path expected by the app
    credentials_file = 'google_credentials.json'
    with open(credentials_file, 'w') as f:
        json.dump(credentials_data, f, indent=2)
    
    print(f"✅ Created {credentials_file} with proper format")
    print(f"📁 Update your .env file to point to: {os.path.abspath(credentials_file)}")
    
    # Update .env file automatically
    update_env_file(credentials_file)

def update_env_file(credentials_file):
    """Update the .env file with the credentials file path."""
    env_file = '.env'
    if not os.path.exists(env_file):
        print("❌ .env file not found")
        return
    
    # Read current .env file
    with open(env_file, 'r') as f:
        lines = f.readlines()
    
    # Update the credentials file paths
    updated_lines = []
    for line in lines:
        if line.startswith('GOOGLE_CALENDAR_CREDENTIALS_FILE='):
            updated_lines.append(f'GOOGLE_CALENDAR_CREDENTIALS_FILE={os.path.abspath(credentials_file)}\n')
        elif line.startswith('GMAIL_CREDENTIALS_FILE='):
            updated_lines.append(f'GMAIL_CREDENTIALS_FILE={os.path.abspath(credentials_file)}\n')
        else:
            updated_lines.append(line)
    
    # Write back to .env file
    with open(env_file, 'w') as f:
        f.writelines(updated_lines)
    
    print("✅ Updated .env file with credentials file paths")

if __name__ == "__main__":
    print("🚀 Google OAuth Setup Helper")
    print("=" * 40)
    
    try:
        # Set up OAuth
        setup_oauth()
        
        # Create credentials file
        create_credentials_file()
        
        print("\n🎉 Setup complete! Your Morning Brief app should now be able to:")
        print("   📅 Access your Google Calendar")
        print("   📧 Send emails via Gmail")
        
    except Exception as e:
        print(f"❌ Error during setup: {e}")
        print("Please check the instructions and try again.") 