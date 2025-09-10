#!/usr/bin/env python3
"""
Manual Gmail Authentication Script
Run this to authenticate with Gmail API
"""

import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.labels',
    'https://www.googleapis.com/auth/gmail.metadata'
]

def authenticate():
    """Perform Gmail authentication"""
    creds = None
    token_path = '/home/ubuntu/token.json'
    credentials_path = '/home/ubuntu/credentials.json'
    
    if not os.path.exists(credentials_path):
        print("❌ credentials.json not found!")
        print("Please download it from Google Cloud Console")
        return False
    
    # Check existing token
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # Get new credentials if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("✅ Token refreshed successfully")
            except Exception as e:
                print(f"Token refresh failed: {e}")
                creds = None
        
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            print("✅ New authentication completed")
    
    # Save credentials
    with open(token_path, 'w') as token:
        token.write(creds.to_json())
    
    # Test the connection
    try:
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        print(f"✅ Successfully authenticated as: {profile.get('emailAddress')}")
        return True
    except Exception as e:
        print(f"❌ Authentication test failed: {e}")
        return False

if __name__ == '__main__':
    print("🔐 Gmail Authentication Setup")
    print("============================")
    success = authenticate()
    if success:
        print("\n🎉 Authentication setup complete!")
        print("You can now run the email processor.")
    else:
        print("\n❌ Authentication setup failed.")
        sys.exit(1)
