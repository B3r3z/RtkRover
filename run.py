#!/usr/bin/env python3
"""
RTK Mower Flask Application Entry Point
"""

import sys
import os
import logging

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

# Create Flask app
app = create_app()

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run development server
    print("🚜 Starting RTK Mower Web Interface...")
    print("📍 RTK GPS tracking system initializing...")
    print("🌐 Web interface will be available at: http://0.0.0.0:5000")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,  # Disable debug mode to prevent double initialization
        threaded=True
    )
