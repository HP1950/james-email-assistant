# Gmail Assistant - Automated Email Processing System

## Overview

The Gmail Assistant Email Processing System is a comprehensive automation solution that runs 3 times daily (8 AM, 1 PM, 6 PM UTC) to automatically manage your Gmail inbox. It provides intelligent email organization, spam detection, unsubscribe management, and AI-powered response draft generation.

## Features

### 🔄 Automated Processing (3x Daily)
- **Morning Run (8 AM UTC)**: Process overnight emails
- **Afternoon Run (1 PM UTC)**: Handle midday correspondence  
- **Evening Run (6 PM UTC)**: Organize end-of-day emails

### 🛡️ Smart Spam Detection
- Keyword-based spam filtering
- Suspicious domain detection
- Heuristic analysis (caps, urgency, etc.)
- Automatic spam deletion with logging

### 📂 Intelligent Email Categorization
- **Business**: Meetings, projects, contracts, invoices
- **Personal**: Family, friends, personal matters
- **Promotional**: Sales, discounts, marketing emails
- **Social**: Social media notifications
- **Other**: Uncategorized emails

### 🏷️ Gmail Label Management
- Automatic label application based on categories
- Custom label creation and management
- Integration with Gmail's built-in category system

### 📧 Unsubscribe Detection & Management
- Identifies promotional emails with unsubscribe links
- Flags emails for manual unsubscribe review
- Extracts unsubscribe URLs for easy access
- Safe domain filtering to avoid legitimate services

### 🤖 AI-Powered Response Drafts
- Generates contextual response drafts for important emails
- Confidence scoring for response quality
- Multiple response types (meetings, questions, requests, etc.)
- **All drafts require manual approval** - never sends automatically

### 📊 Comprehensive Analytics
- Daily processing statistics
- Email category breakdowns
- Performance metrics and timing
- Error tracking and reporting

### 🔍 Activity Logging
- Detailed logs of all processing activities
- Decision tracking for transparency
- Error logging for troubleshooting
- Processing time metrics

## System Architecture

### Core Components

1. **email_processor.py** - Main processing engine
2. **email_processor_daemon.py** - Scheduled execution wrapper
3. **email_processor_config.json** - Configuration settings
4. **PostgreSQL Database** - Data storage and analytics
5. **Gmail API Integration** - Email access and manipulation

### Database Schema

The system uses the existing Gmail Assistant dashboard database with these tables:

- `email_drafts` - AI-generated response drafts awaiting approval
- `automation_rules` - Custom processing rules and triggers
- `activity_logs` - Detailed processing activity records
- `user_settings` - User preferences and configuration
- `email_statistics` - Daily processing statistics and metrics

## Configuration

### Main Configuration File: `/home/ubuntu/email_processor_config.json`

```json
{
  "processing_limits": {
    "max_emails_per_run": 100,
    "max_drafts_per_run": 20,
    "max_processing_time_minutes": 30,
    "rate_limit_delay": 0.1
  },
  "spam_detection": {
    "enabled": true,
    "sensitivity": "medium",
    "keywords": [...],
    "suspicious_domains": [...]
  },
  "ai_response": {
    "enabled": true,
    "confidence_threshold": 0.7,
    "require_approval": true
  }
}
```

### Spam Detection Settings

- **Sensitivity Levels**: low (0.8), medium (0.6), high (0.4)
- **Keyword Matching**: Configurable spam keyword list
- **Domain Filtering**: Suspicious domain detection
- **Heuristic Analysis**: Caps ratio, urgency language, etc.

### AI Response Configuration

- **Confidence Threshold**: Minimum confidence for draft creation
- **Response Types**: Meeting, question, request, acknowledgment, general
- **Template System**: Customizable response templates
- **Approval Required**: All drafts saved for manual review

## Installation & Setup

### Prerequisites

1. **Gmail API Credentials**
   - Google Cloud Console project with Gmail API enabled
   - OAuth2 credentials downloaded as `credentials.json`
   - Place in `/home/ubuntu/credentials.json`

2. **Database Access**
   - PostgreSQL database with Gmail Assistant schema
   - Connection configured in environment variables

3. **Python Dependencies**
   - All dependencies installed via `requirements_email_processor.txt`

### Setup Steps

1. **Install Dependencies**
   ```bash
   pip install -r /home/ubuntu/requirements_email_processor.txt
   ```

2. **Configure Gmail Authentication**
   ```bash
   python3 /home/ubuntu/authenticate_gmail.py
   ```

3. **Test the System**
   ```bash
   bash /home/ubuntu/test_email_processor.sh
   ```

4. **Verify Scheduled Task**
   - Task runs automatically 3x daily
   - Check logs in `/home/ubuntu/email_processor_logs/`

## Usage

### Automatic Operation

The system runs automatically on the following schedule:
- **8:00 AM UTC** - Morning processing
- **1:00 PM UTC** - Afternoon processing  
- **6:00 PM UTC** - Evening processing

### Manual Execution

For testing or immediate processing:

```bash
cd /home/ubuntu
python3 email_processor_daemon.py
```

### Monitoring

1. **Log Files**: `/home/ubuntu/email_processor_logs/`
   - Daily processing logs
   - Error reports
   - Activity summaries

2. **Status File**: `/home/ubuntu/email_processor_status.json`
   - Last run timestamp
   - Success/failure status
   - Next scheduled run

3. **Dashboard Integration**
   - View statistics in the Gmail Assistant dashboard
   - Review and approve AI-generated drafts
   - Monitor processing activity

## Security & Privacy

### Data Protection
- All processing happens locally on your server
- No email content sent to external AI services
- Gmail API credentials stored securely
- Database access restricted to application

### Authentication
- OAuth2 flow for Gmail API access
- Automatic token refresh handling
- Secure credential storage

### Permissions
- Read access to Gmail messages
- Label modification permissions
- Draft creation capabilities
- **No automatic sending** - all responses require approval

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Run `python3 /home/ubuntu/authenticate_gmail.py`
   - Check credentials.json file exists
   - Verify Gmail API is enabled in Google Cloud Console

2. **Database Connection Issues**
   - Verify DATABASE_URL environment variable
   - Check PostgreSQL service status
   - Ensure database schema is up to date

3. **Rate Limiting**
   - System includes automatic rate limiting
   - Adjust `rate_limit_delay` in config if needed
   - Monitor Gmail API quota usage

4. **Processing Errors**
   - Check logs in `/home/ubuntu/email_processor_logs/`
   - Review error messages in activity logs
   - Verify email content parsing

### Log Analysis

**Daily Logs**: `/home/ubuntu/email_processor_logs/daemon_YYYYMMDD.log`
- Processing start/end times
- Email counts and categories
- Error messages and stack traces
- Performance metrics

**Summary Reports**: `/home/ubuntu/email_processor_logs/summary_YYYYMMDD_HHMM.txt`
- Processing statistics
- Category breakdowns
- Action summaries

## Performance Metrics

### Typical Processing Times
- **Small inbox** (< 50 emails): 30-60 seconds
- **Medium inbox** (50-200 emails): 1-3 minutes
- **Large inbox** (200+ emails): 3-5 minutes

### Rate Limits
- Gmail API: 250 quota units per second
- Processing delay: 0.1 seconds between emails
- Batch operations: Up to 1000 emails per request

### Resource Usage
- **Memory**: ~50-100 MB during processing
- **CPU**: Low usage with rate limiting
- **Network**: Minimal bandwidth for API calls
- **Storage**: Log files ~1-5 MB per day

## Customization

### Adding Custom Rules

Edit `/home/ubuntu/email_processor_config.json`:

```json
{
  "categorization": {
    "business_keywords": ["your", "custom", "keywords"],
    "custom_categories": {
      "finance": ["invoice", "payment", "billing"],
      "travel": ["flight", "hotel", "booking"]
    }
  }
}
```

### Response Templates

Customize AI response templates:

```json
{
  "ai_response": {
    "response_templates": {
      "meeting_response": "Your custom meeting response template",
      "custom_type": "Your custom response template"
    }
  }
}
```

### Spam Detection Tuning

Adjust spam detection sensitivity:

```json
{
  "spam_detection": {
    "sensitivity": "high",  // low, medium, high
    "custom_keywords": ["your", "spam", "keywords"],
    "whitelist_domains": ["trusted-domain.com"]
  }
}
```

## Support & Maintenance

### Regular Maintenance
- Monitor log files for errors
- Review and approve AI-generated drafts
- Update spam detection keywords as needed
- Check Gmail API quota usage

### Updates
- System automatically handles Gmail API changes
- Configuration updates can be made without restart
- Database schema migrations handled by dashboard app

### Backup
- Configuration files: `/home/ubuntu/email_processor_config.json`
- Credentials: `/home/ubuntu/credentials.json`, `/home/ubuntu/token.json`
- Logs: `/home/ubuntu/email_processor_logs/`
- Database: Handled by dashboard application

## Integration with Dashboard

The email processor integrates seamlessly with the Gmail Assistant Dashboard:

1. **Draft Review**: View and approve AI-generated drafts
2. **Statistics**: Real-time processing metrics and analytics
3. **Activity Monitoring**: Detailed logs and activity tracking
4. **Configuration**: Manage settings through web interface
5. **Status Monitoring**: System health and processing status

## Conclusion

The Gmail Assistant Email Processing System provides comprehensive, automated email management while maintaining full user control over important decisions. The system processes emails intelligently, provides useful automation, and ensures all critical actions require human approval.

For support or questions, check the log files and dashboard for detailed information about system operation and performance.
