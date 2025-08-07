#!/usr/bin/env python3
"""
Production runner for RTK Mower
Runs without Flask debug mode to avoid double initialization
"""

import os
import sys
from app import create_app

if __name__ == '__main__':
    app = create_app()
    
    # Production mode - no reloader
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,  # No debug mode to avoid double startup
        use_reloader=False  # Explicitly disable reloader
    )
