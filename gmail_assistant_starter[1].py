#!/usr/bin/env python3
"""
Gmail Assistant Starter Template
A production-ready foundation for the automated email assistant

This template includes:
- OAuth authentication with token refresh
- Rate limiting and error handling
- Core email management functions
- Batch operations for efficiency
- Logging and monitoring hooks
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gmail_assistant.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Gmail API configuration
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.labels',
    'https://www.googleapis.com/auth/gmail.metadata'
]

@dataclass
class EmailAction:
    """Represents an action to be taken on an email"""
    message_id: str
    action_type: str  # 'label', 'delete', 'archive', 'mark_read'
    parameters: Dict[str, Any]

@dataclass
class ProcessingStats:
    """Statistics for email processing session"""
    total_processed: int = 0
    organized: int = 0
    spam_deleted: int = 0
    unsubscribe_found: int = 0
    drafts_created: int = 0
    errors: int = 0

class GmailAssistant:
    """Main Gmail Assistant class"""
    
    def __init__(self, credentials_path: str = 'credentials.json', token_path: str = 'token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.rate_limiter = RateLimiter(requests_per_second=4)  # Conservative rate limiting
        
    def authenticate(self) -> bool:
        """Authenticate with Gmail API"""
        try:
            creds = None
            
            # Load existing token
            if os.path.exists(self.token_path):
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            
            # Refresh or get new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired token...")
                    creds.refresh(Request())
                else:
                    logger.info("Getting new credentials...")
                    if not os.path.exists(self.credentials_path):
                        logger.error(f"Credentials file not found: {self.credentials_path}")
                        return False
                    
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Save credentials
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
            
            # Build service
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    def get_unread_emails(self, max_results: int = 100) -> List[Dict]:
        """Get unread emails for processing"""
        try:
            self.rate_limiter.wait()
            result = self.service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=max_results
            ).execute()
            
            messages = result.get('messages', [])
            logger.info(f"Found {len(messages)} unread emails")
            return messages
            
        except HttpError as e:
            logger.error(f"Failed to get unread emails: {e}")
            return []
    
    def get_message_details(self, message_id: str) -> Optional[Dict]:
        """Get full message details"""
        try:
            self.rate_limiter.wait()
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            return message
            
        except HttpError as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            return None
    
    def search_emails(self, query: str, max_results: int = 100) -> List[Dict]:
        """Search emails with Gmail query syntax"""
        try:
            self.rate_limiter.wait()
            result = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = result.get('messages', [])
            logger.info(f"Search '{query}' found {len(messages)} emails")
            return messages
            
        except HttpError as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []
    
    def batch_modify_messages(self, message_ids: List[str], add_labels: List[str] = None, 
                            remove_labels: List[str] = None) -> bool:
        """Batch modify message labels"""
        if not message_ids:
            return True
            
        try:
            self.rate_limiter.wait()
            
            # Gmail API batch modify
            body = {
                'ids': message_ids,
                'addLabelIds': add_labels or [],
                'removeLabelIds': remove_labels or []
            }
            
            self.service.users().messages().batchModify(userId='me', body=body).execute()
            logger.info(f"Batch modified {len(message_ids)} messages")
            return True
            
        except HttpError as e:
            logger.error(f"Batch modify failed: {e}")
            return False
    
    def create_draft_response(self, original_message_id: str, response_content: str, 
                            subject: str = None) -> Optional[str]:
        """Create a draft response to an email"""
        try:
            # Get original message for reply context
            original = self.get_message_details(original_message_id)
            if not original:
                return None
            
            # Extract headers
            headers = {h['name']: h['value'] for h in original['payload'].get('headers', [])}
            
            # Create draft message
            draft_message = self._create_reply_message(
                to=headers.get('From', ''),
                subject=subject or f"Re: {headers.get('Subject', '')}",
                body=response_content,
                thread_id=original.get('threadId')
            )
            
            self.rate_limiter.wait()
            draft = self.service.users().drafts().create(
                userId='me',
                body={'message': draft_message}
            ).execute()
            
            draft_id = draft['id']
            logger.info(f"Created draft response {draft_id} for message {original_message_id}")
            return draft_id
            
        except HttpError as e:
            logger.error(f"Failed to create draft: {e}")
            return None
    
    def organize_emails(self, stats: ProcessingStats) -> None:
        """Main email organization logic"""
        logger.info("Starting email organization...")
        
        # Get unread emails
        unread_messages = self.get_unread_emails()
        stats.total_processed = len(unread_messages)
        
        # Process in batches for efficiency
        batch_size = 50
        for i in range(0, len(unread_messages), batch_size):
            batch = unread_messages[i:i + batch_size]
            self._process_email_batch(batch, stats)
        
        logger.info(f"Email organization complete. Processed: {stats.total_processed}")
    
    def _process_email_batch(self, message_batch: List[Dict], stats: ProcessingStats) -> None:
        """Process a batch of emails"""
        actions = []
        
        for msg in message_batch:
            message_id = msg['id']
            
            # Get full message details
            details = self.get_message_details(message_id)
            if not details:
                stats.errors += 1
                continue
            
            # Analyze email and determine actions
            email_actions = self._analyze_email(details)
            actions.extend(email_actions)
        
        # Execute actions in batches
        self._execute_actions(actions, stats)
    
    def _analyze_email(self, message: Dict) -> List[EmailAction]:
        """Analyze email and determine what actions to take"""
        actions = []
        message_id = message['id']
        
        # Extract headers and content
        headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
        subject = headers.get('Subject', '').lower()
        sender = headers.get('From', '').lower()
        
        # Spam detection
        if self._is_spam(subject, sender):
            actions.append(EmailAction(
                message_id=message_id,
                action_type='delete',
                parameters={}
            ))
            return actions
        
        # Newsletter/unsubscribe detection
        if 'unsubscribe' in subject or 'newsletter' in subject:
            actions.append(EmailAction(
                message_id=message_id,
                action_type='label',
                parameters={'add_labels': ['CATEGORY_PROMOTIONS']}
            ))
        
        # Work email detection
        if any(domain in sender for domain in ['@company.com', '@work.org']):
            actions.append(EmailAction(
                message_id=message_id,
                action_type='label',
                parameters={'add_labels': ['Work']}
            ))
        
        # Mark as read if processed
        actions.append(EmailAction(
            message_id=message_id,
            action_type='mark_read',
            parameters={}
        ))
        
        return actions
    
    def _is_spam(self, subject: str, sender: str) -> bool:
        """Simple spam detection heuristics"""
        spam_indicators = [
            'limited time offer',
            'act now',
            'free money',
            'click here now',
            'congratulations you won'
        ]
        
        suspicious_domains = [
            'suspicious-domain.com',
            'spam-sender.net'
        ]
        
        # Check subject for spam indicators
        if any(indicator in subject for indicator in spam_indicators):
            return True
        
        # Check sender domain
        if any(domain in sender for domain in suspicious_domains):
            return True
        
        return False
    
    def _execute_actions(self, actions: List[EmailAction], stats: ProcessingStats) -> None:
        """Execute email actions in batches"""
        # Group actions by type for batch processing
        label_actions = {}
        delete_ids = []
        mark_read_ids = []
        
        for action in actions:
            if action.action_type == 'label':
                labels_key = str(sorted(action.parameters.get('add_labels', [])))
                if labels_key not in label_actions:
                    label_actions[labels_key] = []
                label_actions[labels_key].append(action.message_id)
            elif action.action_type == 'delete':
                delete_ids.append(action.message_id)
            elif action.action_type == 'mark_read':
                mark_read_ids.append(action.message_id)
        
        # Execute batch operations
        try:
            # Batch label operations
            for labels_str, message_ids in label_actions.items():
                labels = eval(labels_str) if labels_str != '[]' else []
                if self.batch_modify_messages(message_ids, add_labels=labels):
                    stats.organized += len(message_ids)
            
            # Batch delete (move to trash)
            if delete_ids and self.batch_modify_messages(delete_ids, add_labels=['TRASH']):
                stats.spam_deleted += len(delete_ids)
            
            # Batch mark as read
            if mark_read_ids and self.batch_modify_messages(mark_read_ids, remove_labels=['UNREAD']):
                pass  # Already counted in organized
                
        except Exception as e:
            logger.error(f"Failed to execute actions: {e}")
            stats.errors += len(actions)
    
    def _create_reply_message(self, to: str, subject: str, body: str, thread_id: str = None) -> Dict:
        """Create a reply message structure"""
        import base64
        import email.mime.text
        
        msg = email.mime.text.MIMEText(body)
        msg['To'] = to
        msg['Subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        
        message = {'raw': raw_message}
        if thread_id:
            message['threadId'] = thread_id
            
        return message
    
    def run_daily_processing(self) -> ProcessingStats:
        """Run the daily email processing routine"""
        logger.info("=== Starting Daily Email Processing ===")
        stats = ProcessingStats()
        
        try:
            if not self.authenticate():
                logger.error("Authentication failed")
                return stats
            
            # Main processing steps
            self.organize_emails(stats)
            
            # TODO: Add other processing steps
            # - Unsubscribe detection and processing
            # - AI response generation
            # - Spam analysis and reporting
            
            logger.info(f"=== Daily Processing Complete ===")
            logger.info(f"Stats: {stats}")
            
        except Exception as e:
            logger.error(f"Daily processing failed: {e}")
            stats.errors += 1
        
        return stats

class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, requests_per_second: float):
        self.min_interval = 1.0 / requests_per_second
        self.last_request = 0
    
    def wait(self):
        """Wait if necessary to respect rate limits"""
        now = time.time()
        time_since_last = now - self.last_request
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request = time.time()

def main():
    """Main entry point for the Gmail Assistant"""
    assistant = GmailAssistant()
    stats = assistant.run_daily_processing()
    
    # Log final statistics
    print(f"\n=== Processing Summary ===")
    print(f"Total emails processed: {stats.total_processed}")
    print(f"Emails organized: {stats.organized}")
    print(f"Spam deleted: {stats.spam_deleted}")
    print(f"Unsubscribe emails found: {stats.unsubscribe_found}")
    print(f"Drafts created: {stats.drafts_created}")
    print(f"Errors: {stats.errors}")

if __name__ == '__main__':
    main()
