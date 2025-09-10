#!/usr/bin/env python3
"""
Email Processor Daemon Script
Optimized version for scheduled execution with better error handling
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Set environment variables
os.environ['DATABASE_URL'] = "postgresql://role_13f863f614:uMSlmglksxluebz3G6u8nrS7B7hlpMQS@db-13f863f614.db001.hosteddb.reai.io:5432/13f863f614"
os.environ['PYTHONPATH'] = "/home/ubuntu"

def setup_logging():
    """Setup logging for daemon execution"""
    log_dir = Path("/home/ubuntu/email_processor_logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"daemon_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

def check_prerequisites():
    """Check if all prerequisites are met"""
    logger = logging.getLogger(__name__)
    
    # Check credentials
    if not os.path.exists('/home/ubuntu/credentials.json'):
        logger.error("Gmail credentials.json not found")
        return False
    
    if not os.path.exists('/home/ubuntu/token.json'):
        logger.warning("Gmail token.json not found - authentication may be needed")
    
    # Check database connection
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
    
    return True

def run_email_processor():
    """Run the email processor with error handling"""
    logger = setup_logging()
    
    try:
        logger.info("=== Email Processor Daemon Starting ===")
        
        # Check prerequisites
        if not check_prerequisites():
            logger.error("Prerequisites check failed")
            return False
        
        # Import and run processor
        sys.path.insert(0, '/home/ubuntu')
        from email_processor import EmailProcessor
        
        processor = EmailProcessor()
        success = processor.run()
        
        if success:
            logger.info("=== Email Processing Completed Successfully ===")
        else:
            logger.error("=== Email Processing Failed ===")
        
        return success
        
    except Exception as e:
        logger.error(f"Fatal error in email processor daemon: {e}")
        return False

def create_status_file(success: bool):
    """Create status file for monitoring"""
    status_data = {
        "last_run": datetime.now().isoformat(),
        "success": success,
        "next_scheduled": "Managed by scheduler"
    }
    
    with open("/home/ubuntu/email_processor_status.json", 'w') as f:
        json.dump(status_data, f, indent=2)

def main():
    """Main daemon entry point"""
    success = run_email_processor()
    create_status_file(success)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
