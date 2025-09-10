#!/usr/bin/env python3
"""
Gmail Assistant - Automated Email Processing System
Runs 3 times daily to process emails automatically
"""

import os
import sys
import json
import time
import logging
import sqlite3
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
import base64
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from urllib.parse import urljoin, urlparse

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.labels',
    'https://www.googleapis.com/auth/gmail.metadata'
]

class EmailProcessor:
    def __init__(self, config_path: str = "/home/ubuntu/email_processor_config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.gmail_service = None
        self.db_connection = None
        self.logger = self.setup_logging()
        self.processing_stats = {
            'emails_processed': 0,
            'drafts_created': 0,
            'spam_deleted': 0,
            'unsubscribe_actions': 0,
            'rules_triggered': 0,
            'errors': 0,
            'start_time': datetime.now(),
            'categories': {
                'business': 0,
                'personal': 0,
                'promotional': 0,
                'social': 0,
                'other': 0
            }
        }
        
    def load_config(self) -> Dict:
        """Load configuration from file"""
        default_config = {
            "database_url": os.getenv("DATABASE_URL", "postgresql://localhost/gmail_assistant"),
            "gmail_credentials_path": "/home/ubuntu/credentials.json",
            "gmail_token_path": "/home/ubuntu/token.json",
            "processing_limits": {
                "max_emails_per_run": 100,
                "max_drafts_per_run": 20,
                "max_processing_time_minutes": 30,
                "rate_limit_delay": 0.1
            },
            "spam_detection": {
                "enabled": True,
                "sensitivity": "medium",
                "keywords": [
                    "lottery", "winner", "congratulations", "claim now", "urgent",
                    "limited time", "act now", "free money", "guaranteed",
                    "no obligation", "risk free", "100% free", "click here now"
                ],
                "suspicious_domains": [
                    "tempmail.org", "10minutemail.com", "guerrillamail.com"
                ]
            },
            "unsubscribe_detection": {
                "enabled": True,
                "keywords": ["unsubscribe", "opt out", "remove me", "stop emails"],
                "auto_unsubscribe": False,
                "flag_for_review": True
            },
            "categorization": {
                "business_keywords": ["meeting", "project", "deadline", "invoice", "contract"],
                "personal_keywords": ["family", "friend", "birthday", "vacation", "personal"],
                "promotional_keywords": ["sale", "discount", "offer", "deal", "promotion"],
                "social_keywords": ["facebook", "twitter", "linkedin", "instagram", "notification"]
            },
            "ai_response": {
                "enabled": True,
                "confidence_threshold": 0.7,
                "max_response_length": 500,
                "require_approval": True
            }
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
        
        return default_config
    
    def setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        log_dir = "/home/ubuntu/email_processor_logs"
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f"email_processor_{datetime.now().strftime('%Y%m%d')}.log")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        return logging.getLogger(__name__)
    
    def authenticate_gmail(self) -> bool:
        """Authenticate with Gmail API"""
        try:
            creds = None
            token_path = self.config['gmail_token_path']
            credentials_path = self.config['gmail_credentials_path']
            
            # Load existing token
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
            # Refresh or get new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        self.logger.info("Gmail token refreshed successfully")
                    except Exception as e:
                        self.logger.error(f"Token refresh failed: {e}")
                        return False
                else:
                    self.logger.error("No valid Gmail credentials found. Please run authentication setup.")
                    return False
            
            # Save credentials
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            
            # Build Gmail service
            self.gmail_service = build('gmail', 'v1', credentials=creds)
            self.logger.info("Gmail authentication successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Gmail authentication failed: {e}")
            return False
    
    def connect_database(self) -> bool:
        """Connect to PostgreSQL database"""
        try:
            self.db_connection = psycopg2.connect(self.config['database_url'])
            self.logger.info("Database connection established")
            return True
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            return False
    
    def get_last_processing_time(self) -> Optional[datetime]:
        """Get the timestamp of the last processing run"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                SELECT MAX("createdAt") FROM activity_logs 
                WHERE "actionType" = 'email_processing_completed'
            """)
            result = cursor.fetchone()
            return result[0] if result[0] else datetime.now() - timedelta(hours=8)
        except Exception as e:
            self.logger.error(f"Error getting last processing time: {e}")
            return datetime.now() - timedelta(hours=8)
    
    def fetch_new_emails(self, since: datetime) -> List[Dict]:
        """Fetch new emails since the last processing run"""
        try:
            # Convert datetime to Gmail query format
            query_date = since.strftime('%Y/%m/%d')
            query = f'after:{query_date} -in:sent -in:draft'
            
            self.logger.info(f"Fetching emails since {since}")
            
            # Get message list
            messages_result = self.gmail_service.users().messages().list(
                userId='me',
                q=query,
                maxResults=self.config['processing_limits']['max_emails_per_run']
            ).execute()
            
            messages = messages_result.get('messages', [])
            self.logger.info(f"Found {len(messages)} new emails to process")
            
            # Fetch full message details
            emails = []
            for msg in messages:
                try:
                    time.sleep(self.config['processing_limits']['rate_limit_delay'])
                    
                    message = self.gmail_service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='full'
                    ).execute()
                    
                    emails.append(self.parse_email_message(message))
                    
                except Exception as e:
                    self.logger.error(f"Error fetching message {msg['id']}: {e}")
                    self.processing_stats['errors'] += 1
            
            return emails
            
        except Exception as e:
            self.logger.error(f"Error fetching emails: {e}")
            return []
    
    def parse_email_message(self, message: Dict) -> Dict:
        """Parse Gmail message into structured format"""
        headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
        
        # Extract body content
        body = self.extract_email_body(message['payload'])
        
        return {
            'id': message['id'],
            'thread_id': message['threadId'],
            'label_ids': message.get('labelIds', []),
            'sender': headers.get('From', ''),
            'recipient': headers.get('To', ''),
            'subject': headers.get('Subject', ''),
            'date': headers.get('Date', ''),
            'body': body,
            'headers': headers,
            'snippet': message.get('snippet', ''),
            'size_estimate': message.get('sizeEstimate', 0)
        }
    
    def extract_email_body(self, payload: Dict) -> str:
        """Extract text content from email payload"""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif part['mimeType'] == 'text/html' and not body:
                    data = part['body'].get('data', '')
                    if data:
                        html_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        # Simple HTML to text conversion
                        body += re.sub(r'<[^>]+>', '', html_content)
        else:
            if payload['mimeType'] == 'text/plain':
                data = payload['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        return body.strip()
    
    def categorize_email(self, email: Dict) -> str:
        """Categorize email based on content and sender"""
        subject = email['subject'].lower()
        body = email['body'].lower()
        sender = email['sender'].lower()
        
        # Check business keywords
        business_keywords = self.config['categorization']['business_keywords']
        if any(keyword in subject or keyword in body for keyword in business_keywords):
            return 'business'
        
        # Check promotional keywords
        promotional_keywords = self.config['categorization']['promotional_keywords']
        if any(keyword in subject or keyword in body for keyword in promotional_keywords):
            return 'promotional'
        
        # Check social keywords
        social_keywords = self.config['categorization']['social_keywords']
        if any(keyword in sender for keyword in social_keywords):
            return 'social'
        
        # Check personal keywords
        personal_keywords = self.config['categorization']['personal_keywords']
        if any(keyword in subject or keyword in body for keyword in personal_keywords):
            return 'personal'
        
        return 'other'
    
    def detect_spam(self, email: Dict) -> Tuple[bool, float, str]:
        """Detect if email is spam using heuristics"""
        if not self.config['spam_detection']['enabled']:
            return False, 0.0, "Spam detection disabled"
        
        spam_score = 0.0
        reasons = []
        
        subject = email['subject'].lower()
        body = email['body'].lower()
        sender = email['sender'].lower()
        
        # Check spam keywords
        spam_keywords = self.config['spam_detection']['keywords']
        keyword_matches = sum(1 for keyword in spam_keywords if keyword in subject or keyword in body)
        if keyword_matches > 0:
            spam_score += keyword_matches * 0.2
            reasons.append(f"Contains {keyword_matches} spam keywords")
        
        # Check suspicious domains
        suspicious_domains = self.config['spam_detection']['suspicious_domains']
        for domain in suspicious_domains:
            if domain in sender:
                spam_score += 0.5
                reasons.append(f"Suspicious sender domain: {domain}")
        
        # Check for excessive caps
        caps_ratio = sum(1 for c in subject if c.isupper()) / max(len(subject), 1)
        if caps_ratio > 0.5:
            spam_score += 0.3
            reasons.append("Excessive capital letters")
        
        # Check for multiple exclamation marks
        if subject.count('!') > 2:
            spam_score += 0.2
            reasons.append("Multiple exclamation marks")
        
        # Check for urgent language
        urgent_phrases = ["urgent", "immediate", "act now", "limited time"]
        if any(phrase in subject or phrase in body for phrase in urgent_phrases):
            spam_score += 0.3
            reasons.append("Contains urgent language")
        
        # Determine if spam based on sensitivity
        sensitivity = self.config['spam_detection']['sensitivity']
        thresholds = {'low': 0.8, 'medium': 0.6, 'high': 0.4}
        threshold = thresholds.get(sensitivity, 0.6)
        
        is_spam = spam_score >= threshold
        reason_text = "; ".join(reasons) if reasons else "No spam indicators"
        
        return is_spam, spam_score, reason_text
    
    def detect_unsubscribe_opportunity(self, email: Dict) -> Tuple[bool, List[str]]:
        """Detect if email contains unsubscribe opportunities"""
        if not self.config['unsubscribe_detection']['enabled']:
            return False, []
        
        body = email['body'].lower()
        unsubscribe_links = []
        
        # Look for unsubscribe keywords
        keywords = self.config['unsubscribe_detection']['keywords']
        has_unsubscribe_text = any(keyword in body for keyword in keywords)
        
        if has_unsubscribe_text:
            # Extract potential unsubscribe URLs
            url_pattern = r'https?://[^\s<>"]+(?:unsubscribe|opt[_-]?out|remove)[^\s<>"]*'
            urls = re.findall(url_pattern, email['body'], re.IGNORECASE)
            unsubscribe_links.extend(urls)
            
            # Look for mailto unsubscribe links
            mailto_pattern = r'mailto:[^\s<>"]+(?:unsubscribe|remove)[^\s<>"]*'
            mailto_links = re.findall(mailto_pattern, email['body'], re.IGNORECASE)
            unsubscribe_links.extend(mailto_links)
        
        return len(unsubscribe_links) > 0, unsubscribe_links
    
    def apply_gmail_labels(self, email_id: str, labels_to_add: List[str], labels_to_remove: List[str] = None):
        """Apply labels to Gmail message"""
        try:
            if labels_to_remove is None:
                labels_to_remove = []
            
            modify_request = {
                'addLabelIds': labels_to_add,
                'removeLabelIds': labels_to_remove
            }
            
            self.gmail_service.users().messages().modify(
                userId='me',
                id=email_id,
                body=modify_request
            ).execute()
            
            self.logger.info(f"Applied labels to email {email_id}: +{labels_to_add}, -{labels_to_remove}")
            
        except Exception as e:
            self.logger.error(f"Error applying labels to email {email_id}: {e}")
    
    def delete_spam_email(self, email_id: str) -> bool:
        """Move email to trash (delete)"""
        try:
            self.gmail_service.users().messages().trash(
                userId='me',
                id=email_id
            ).execute()
            
            self.logger.info(f"Deleted spam email: {email_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error deleting email {email_id}: {e}")
            return False
    
    def generate_ai_response(self, email: Dict) -> Optional[Dict]:
        """Generate AI-powered response draft"""
        if not self.config['ai_response']['enabled']:
            return None
        
        try:
            # Simple response generation based on email content
            subject = email['subject']
            body = email['body']
            sender = email['sender']
            
            # Determine response type based on content
            response_type = self.determine_response_type(email)
            
            if response_type == 'no_response':
                return None
            
            # Generate response based on type
            response_subject, response_body, confidence = self.create_response_content(email, response_type)
            
            if confidence < self.config['ai_response']['confidence_threshold']:
                self.logger.info(f"Response confidence too low ({confidence}) for email {email['id']}")
                return None
            
            return {
                'recipient': sender,
                'recipient_name': self.extract_sender_name(sender),
                'subject': response_subject,
                'body': response_body,
                'original_email_id': email['id'],
                'ai_confidence': confidence,
                'category': self.categorize_email(email),
                'priority': self.determine_priority(email)
            }
            
        except Exception as e:
            self.logger.error(f"Error generating AI response for email {email['id']}: {e}")
            return None
    
    def determine_response_type(self, email: Dict) -> str:
        """Determine what type of response is needed"""
        subject = email['subject'].lower()
        body = email['body'].lower()
        
        # Don't respond to automated emails
        automated_indicators = ['noreply', 'no-reply', 'donotreply', 'automated', 'notification']
        if any(indicator in email['sender'].lower() for indicator in automated_indicators):
            return 'no_response'
        
        # Meeting requests
        if any(word in subject or word in body for word in ['meeting', 'schedule', 'appointment']):
            return 'meeting_response'
        
        # Questions
        if '?' in subject or '?' in body:
            return 'question_response'
        
        # Requests
        if any(word in subject or word in body for word in ['request', 'need', 'help', 'assistance']):
            return 'request_response'
        
        # Thank you emails
        if any(word in subject or word in body for word in ['thank', 'thanks', 'appreciate']):
            return 'acknowledgment'
        
        return 'general_response'
    
    def create_response_content(self, email: Dict, response_type: str) -> Tuple[str, str, float]:
        """Create response content based on type"""
        sender_name = self.extract_sender_name(email['sender'])
        original_subject = email['subject']
        
        # Response templates
        templates = {
            'meeting_response': {
                'subject': f"Re: {original_subject}",
                'body': f"Hi {sender_name},\n\nThank you for your email regarding the meeting. I'll review my calendar and get back to you with my availability shortly.\n\nBest regards",
                'confidence': 0.8
            },
            'question_response': {
                'subject': f"Re: {original_subject}",
                'body': f"Hi {sender_name},\n\nThank you for your question. I'll need to review this and provide you with a detailed response. I'll get back to you within 24 hours.\n\nBest regards",
                'confidence': 0.7
            },
            'request_response': {
                'subject': f"Re: {original_subject}",
                'body': f"Hi {sender_name},\n\nI've received your request and will review it carefully. I'll respond with more details soon.\n\nThank you for reaching out.\n\nBest regards",
                'confidence': 0.75
            },
            'acknowledgment': {
                'subject': f"Re: {original_subject}",
                'body': f"Hi {sender_name},\n\nYou're very welcome! I'm glad I could help.\n\nBest regards",
                'confidence': 0.9
            },
            'general_response': {
                'subject': f"Re: {original_subject}",
                'body': f"Hi {sender_name},\n\nThank you for your email. I've received it and will respond appropriately soon.\n\nBest regards",
                'confidence': 0.6
            }
        }
        
        template = templates.get(response_type, templates['general_response'])
        return template['subject'], template['body'], template['confidence']
    
    def extract_sender_name(self, sender: str) -> str:
        """Extract name from sender email address"""
        # Try to extract name from "Name <email>" format
        match = re.match(r'^(.+?)\s*<.+>$', sender)
        if match:
            name = match.group(1).strip('"')
            return name if name else "there"
        
        # Extract from email address
        email_match = re.search(r'([^@]+)@', sender)
        if email_match:
            username = email_match.group(1)
            # Convert common patterns to names
            name = username.replace('.', ' ').replace('_', ' ').title()
            return name if len(name) > 1 else "there"
        
        return "there"
    
    def determine_priority(self, email: Dict) -> str:
        """Determine email priority"""
        subject = email['subject'].lower()
        body = email['body'].lower()
        
        # High priority indicators
        high_priority = ['urgent', 'asap', 'important', 'critical', 'emergency']
        if any(word in subject or word in body for word in high_priority):
            return 'high'
        
        # Low priority indicators
        low_priority = ['newsletter', 'promotion', 'marketing', 'unsubscribe']
        if any(word in subject or word in body for word in low_priority):
            return 'low'
        
        return 'medium'
    
    def save_draft_to_database(self, draft: Dict) -> bool:
        """Save generated draft to database for approval"""
        try:
            import secrets
            import string
            
            cursor = self.db_connection.cursor()
            
            # Generate a CUID-like ID
            draft_id = 'draft_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(20))
            
            cursor.execute("""
                INSERT INTO email_drafts (
                    id, recipient, "recipientName", subject, body, "originalEmailId",
                    "aiConfidence", category, priority, "createdAt"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                draft_id,
                draft['recipient'],
                draft['recipient_name'],
                draft['subject'],
                draft['body'],
                draft['original_email_id'],
                draft['ai_confidence'],
                draft['category'],
                draft['priority'],
                datetime.now()
            ))
            
            self.db_connection.commit()
            self.logger.info(f"Saved draft to database for {draft['recipient']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving draft to database: {e}")
            return False
    
    def log_activity(self, action_type: str, description: str, email_id: str = None, 
                    status: str = 'success', metadata: Dict = None, processing_time: int = None):
        """Log activity to database"""
        try:
            import secrets
            import string
            
            cursor = self.db_connection.cursor()
            
            # Generate a CUID-like ID
            log_id = 'log_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(20))
            
            cursor.execute("""
                INSERT INTO activity_logs (
                    id, "actionType", description, "emailId", status, metadata, "processingTime", "createdAt"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                log_id,
                action_type,
                description,
                email_id,
                status,
                json.dumps(metadata) if metadata else None,
                processing_time,
                datetime.now()
            ))
            
            self.db_connection.commit()
            
        except Exception as e:
            self.logger.error(f"Error logging activity: {e}")
    
    def update_statistics(self):
        """Update daily statistics in database"""
        try:
            cursor = self.db_connection.cursor()
            today = datetime.now().date()
            
            # Get or create today's statistics record
            cursor.execute("""
                INSERT INTO email_statistics (date, "createdAt", "updatedAt")
                VALUES (%s, %s, %s)
                ON CONFLICT (date) DO NOTHING
            """, (today, datetime.now(), datetime.now()))
            
            # Update statistics
            stats = self.processing_stats
            processing_time = (datetime.now() - stats['start_time']).total_seconds()
            
            cursor.execute("""
                UPDATE email_statistics SET
                    "emailsProcessed" = "emailsProcessed" + %s,
                    "draftsCreated" = "draftsCreated" + %s,
                    "spamDeleted" = "spamDeleted" + %s,
                    "unsubscribeActions" = "unsubscribeActions" + %s,
                    "rulesTriggered" = "rulesTriggered" + %s,
                    "businessEmails" = "businessEmails" + %s,
                    "personalEmails" = "personalEmails" + %s,
                    "promotionalEmails" = "promotionalEmails" + %s,
                    "socialEmails" = "socialEmails" + %s,
                    "otherEmails" = "otherEmails" + %s,
                    "errorCount" = "errorCount" + %s,
                    "averageProcessingTime" = %s,
                    "updatedAt" = %s
                WHERE date = %s
            """, (
                stats['emails_processed'],
                stats['drafts_created'],
                stats['spam_deleted'],
                stats['unsubscribe_actions'],
                stats['rules_triggered'],
                stats['categories']['business'],
                stats['categories']['personal'],
                stats['categories']['promotional'],
                stats['categories']['social'],
                stats['categories']['other'],
                stats['errors'],
                processing_time,
                datetime.now(),
                today
            ))
            
            self.db_connection.commit()
            self.logger.info("Statistics updated successfully")
            
        except Exception as e:
            self.logger.error(f"Error updating statistics: {e}")
    
    def process_emails(self) -> Dict:
        """Main email processing function"""
        self.logger.info("Starting email processing run")
        
        try:
            # Get last processing time
            last_run = self.get_last_processing_time()
            
            # Fetch new emails
            emails = self.fetch_new_emails(last_run)
            
            if not emails:
                self.logger.info("No new emails to process")
                return self.processing_stats
            
            # Process each email
            for email in emails:
                try:
                    start_time = time.time()
                    
                    # Categorize email
                    category = self.categorize_email(email)
                    self.processing_stats['categories'][category] += 1
                    
                    # Check for spam
                    is_spam, spam_score, spam_reason = self.detect_spam(email)
                    
                    if is_spam:
                        # Delete spam email
                        if self.delete_spam_email(email['id']):
                            self.processing_stats['spam_deleted'] += 1
                            self.log_activity(
                                'spam_deleted',
                                f"Deleted spam email: {email['subject'][:50]}",
                                email['id'],
                                metadata={'spam_score': spam_score, 'reason': spam_reason}
                            )
                        continue
                    
                    # Apply category labels
                    category_labels = {
                        'business': ['CATEGORY_PERSONAL'],  # Gmail's built-in labels
                        'personal': ['CATEGORY_PERSONAL'],
                        'promotional': ['CATEGORY_PROMOTIONS'],
                        'social': ['CATEGORY_SOCIAL']
                    }
                    
                    if category in category_labels:
                        self.apply_gmail_labels(email['id'], category_labels[category])
                    
                    # Check for unsubscribe opportunities
                    has_unsubscribe, unsubscribe_links = self.detect_unsubscribe_opportunity(email)
                    
                    if has_unsubscribe:
                        self.log_activity(
                            'unsubscribe_detected',
                            f"Unsubscribe opportunity found: {email['subject'][:50]}",
                            email['id'],
                            metadata={'links': unsubscribe_links}
                        )
                        self.processing_stats['unsubscribe_actions'] += 1
                    
                    # Generate AI response if needed
                    if category in ['business', 'personal'] and not is_spam:
                        draft = self.generate_ai_response(email)
                        
                        if draft:
                            if self.save_draft_to_database(draft):
                                self.processing_stats['drafts_created'] += 1
                                self.log_activity(
                                    'draft_created',
                                    f"Created draft response for: {email['subject'][:50]}",
                                    email['id'],
                                    metadata={'confidence': draft['ai_confidence']}
                                )
                    
                    # Log processing
                    processing_time = int((time.time() - start_time) * 1000)
                    self.log_activity(
                        'email_processed',
                        f"Processed email: {email['subject'][:50]}",
                        email['id'],
                        metadata={
                            'category': category,
                            'spam_score': spam_score,
                            'has_unsubscribe': has_unsubscribe
                        },
                        processing_time=processing_time
                    )
                    
                    self.processing_stats['emails_processed'] += 1
                    
                    # Rate limiting
                    time.sleep(self.config['processing_limits']['rate_limit_delay'])
                    
                except Exception as e:
                    self.logger.error(f"Error processing email {email.get('id', 'unknown')}: {e}")
                    self.processing_stats['errors'] += 1
            
            # Update statistics
            self.update_statistics()
            
            # Log completion
            self.log_activity(
                'email_processing_completed',
                f"Processing run completed: {self.processing_stats['emails_processed']} emails processed",
                metadata=self.processing_stats
            )
            
            return self.processing_stats
            
        except Exception as e:
            self.logger.error(f"Error in email processing: {e}")
            self.processing_stats['errors'] += 1
            return self.processing_stats
    
    def send_summary_notification(self, stats: Dict):
        """Send summary notification of processing results"""
        try:
            summary = f"""
Email Processing Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 Processing Statistics:
• Emails processed: {stats['emails_processed']}
• Drafts created: {stats['drafts_created']}
• Spam deleted: {stats['spam_deleted']}
• Unsubscribe actions: {stats['unsubscribe_actions']}
• Errors: {stats['errors']}

📂 Categories:
• Business: {stats['categories']['business']}
• Personal: {stats['categories']['personal']}
• Promotional: {stats['categories']['promotional']}
• Social: {stats['categories']['social']}
• Other: {stats['categories']['other']}

⏱️ Processing time: {(datetime.now() - stats['start_time']).total_seconds():.1f} seconds
            """
            
            self.logger.info("Processing summary:")
            self.logger.info(summary)
            
            # Save summary to file for dashboard
            summary_file = f"/home/ubuntu/email_processor_logs/summary_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            with open(summary_file, 'w') as f:
                f.write(summary)
            
        except Exception as e:
            self.logger.error(f"Error sending summary notification: {e}")
    
    def run(self):
        """Main run function"""
        try:
            self.logger.info("=== Gmail Assistant Email Processor Starting ===")
            
            # Authenticate and connect
            if not self.authenticate_gmail():
                self.logger.error("Gmail authentication failed")
                return False
            
            if not self.connect_database():
                self.logger.error("Database connection failed")
                return False
            
            # Process emails
            stats = self.process_emails()
            
            # Send summary
            self.send_summary_notification(stats)
            
            self.logger.info("=== Email Processing Completed Successfully ===")
            return True
            
        except Exception as e:
            self.logger.error(f"Fatal error in email processor: {e}")
            return False
        
        finally:
            # Cleanup
            if self.db_connection:
                self.db_connection.close()

def main():
    """Main entry point"""
    processor = EmailProcessor()
    success = processor.run()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
