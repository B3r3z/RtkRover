#!/usr/bin/env python3
import sys
import os
import logging
import signal
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app

def setup_logging():
    """Setup enhanced logging configuration"""
    log_level = logging.DEBUG if os.getenv('FLASK_DEBUG', 'False').lower() == 'true' else logging.INFO
    
    log_dir = PROJECT_ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # Configure logging
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Add file handler if enabled
    if os.getenv('LOG_TO_FILE', 'False').lower() == 'true':
        file_handler = logging.FileHandler(log_dir / 'rtk_mower.log')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    # Reduce noisy third-party loggers
    logging.getLogger('pynmeagps.nmeareader').setLevel(logging.ERROR)
    logging.getLogger('pynmeagps').setLevel(logging.ERROR)

def setup_signal_handlers(app):
    """Setup graceful shutdown signal handlers"""
    def signal_handler(signum, frame):
        logging.info(f"Received signal {signum}, shutting down gracefully...")
        
        # Try to stop RTK system gracefully
        try:
            from app import app_manager
            rtk_manager = app_manager.get_rtk_manager()
            if rtk_manager and rtk_manager.running:
                logging.info("Stopping RTK system...")
                rtk_manager.stop()
        except Exception as e:
            logging.error(f"Error stopping RTK system: {e}")
        
        logging.info("Shutdown complete")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def validate_environment():
    """Validate environment and configuration"""
    errors = []
    warnings = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        errors.append(f"Python 3.8+ required, got {sys.version}")
    
    # Check required environment variables
    env_file = PROJECT_ROOT / '.env'
    if not env_file.exists():
        warnings.append(".env file not found - using defaults")
    
    # Check if running as root (security warning)
    if os.geteuid() == 0:
        warnings.append("Running as root - consider using non-root user for security")
    
    # Print validation results
    if errors:
        for error in errors:
            logging.error(f"❌ {error}")
        logging.error("Cannot start application due to validation errors")
        sys.exit(1)
    
    if warnings:
        for warning in warnings:
            logging.warning(f"⚠️  {warning}")
    
    logging.info("✅ Environment validation passed")

def main():
    """Main application entry point"""
    # Setup logging first
    setup_logging()
    
    logger = logging.getLogger(__name__)
    logger.info("Rover GPS-RTK starting...")
    
    try:
        # Validate environment
        validate_environment()
        
        # Create Flask app
        logger.info("📍 Initializing RTK GPS tracking system...")
        app = create_app()
        
        # Setup signal handlers for graceful shutdown
        setup_signal_handlers(app)
        
        # Get configuration
        host = os.getenv('FLASK_HOST', '0.0.0.0')
        port = int(os.getenv('FLASK_PORT', '5002'))
        debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        
        # Print startup information
        logger.info("🌐 Web interface configuration:")
        logger.info(f"   Host: {host}")
        logger.info(f"   Port: {port}")
        logger.info(f"   Debug: {debug}")
        logger.info(f"   URLs: http://{host}:{port}")
        if host == '0.0.0.0':
            logger.info(f"         http://localhost:{port}")
        
        # Start the application
        logger.info("🚀 Starting Flask development server...")
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True,
            use_reloader=False  # Disable reloader to avoid issues with RTK threads
        )
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
