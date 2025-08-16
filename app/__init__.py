from flask import Flask, jsonify, render_template
from datetime import datetime
import logging
import threading
import time
import os
from gps.rtk_manager import RTKManager

logger = logging.getLogger(__name__)

class RTKAppError(Exception):
    """Application-specific error for RTK system"""
    pass

class RTKApplicationManager:
    """Thread-safe singleton manager for RTK system"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.rtk_manager = None
            self.rtk_thread = None
            self.initialization_lock = threading.Lock()
            self._initialization_event = threading.Event()
            self._initialized = True
    
    def get_rtk_manager(self):
        """Get RTK manager instance with lazy initialization"""
        # Use a lock to ensure the initialization thread is started only once.
        if not self._initialization_event.is_set():
            with self.initialization_lock:
                # Check again in case another thread initialized it while we were waiting.
                if self.rtk_thread is None:
                    self._init_rtk_system()
            
            # Wait for the initialization to complete with a timeout.
            if not self._initialization_event.wait(timeout=20.0):
                logger.error("RTK system initialization timed out. System will be unavailable.")

        return self.rtk_manager
    
    def _init_rtk_system(self):
        """Initialize RTK system in background thread with proper error handling"""
        def rtk_worker():
            try:
                logger.info("Initializing RTK Manager...")
                self.rtk_manager = RTKManager()
                
                if self.rtk_manager.start():
                    logger.info("RTK system started successfully")
                else:
                    logger.error("Failed to start RTK system - continuing in degraded mode")
                    
            except Exception as e:
                logger.error(f"Critical error in RTK worker thread: {e}", exc_info=True)
                # Set rtk_manager to None to indicate failure
                self.rtk_manager = None
            finally:
                # Signal that initialization is complete, regardless of the outcome.
                self._initialization_event.set()
        
        # Avoid double initialization in Flask debug mode
        if self.rtk_thread is not None and self.rtk_thread.is_alive():
            logger.info("RTK system already initializing, skipping...")
            return
        
        self.rtk_thread = threading.Thread(target=rtk_worker, daemon=True, name="RTKWorker")
        self.rtk_thread.start()

# Global application manager instance
app_manager = RTKApplicationManager()

def create_app():
    """Flask application factory with enhanced security and error handling"""
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # Enhanced Flask configuration
    app.config.update(
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY', os.urandom(24)),
        # Disable debug in production
        DEBUG=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        # Security headers
        SEND_FILE_MAX_AGE_DEFAULT=31536000,  # 1 year for static files
    )
    
    # Setup enhanced logging
    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                # Add file handler for production
                logging.FileHandler('rtk_mower.log') if os.getenv('LOG_TO_FILE') else None
            ]
        )
    
    # Initialize RTK system
    app_manager.get_rtk_manager()
    
    # Register routes with error handling
    _register_routes(app)
    
    # Add error handlers
    _register_error_handlers(app)
    
    return app

def _register_error_handlers(app):
    """Register global error handlers"""
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
    
    @app.errorhandler(RTKAppError)
    def rtk_error(error):
        logger.error(f"RTK application error: {error}")
        return jsonify({"error": str(error)}), 503

def _register_routes(app):
    """Register Flask routes with enhanced error handling and logging"""
    
    @app.route('/')
    def index():
        """Main page with map"""
        return render_template('map.html')
    
    @app.route('/api/position')
    def api_position():
        """Get current GPS position with comprehensive error handling"""
        try:
            rtk_manager = app_manager.get_rtk_manager()
            
            if not rtk_manager:
                logger.warning("RTK system not available for position request")
                return jsonify({
                    "error": "RTK system not initialized",
                    "lat": None,
                    "lon": None,
                    "rtk_status": "System Unavailable",
                    "satellites": 0,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }), 503
            
            position = rtk_manager.get_current_position()
            
            if position and position.get("lat") is not None and position.get("lon") is not None:
                # Validate position data
                lat, lon = position.get("lat"), position.get("lon")
                if abs(lat) > 90 or abs(lon) > 180:
                    logger.warning(f"Invalid GPS coordinates: lat={lat}, lon={lon}")
                    raise RTKAppError("Invalid GPS coordinates received")
                
                return jsonify({
                    "lat": position.get("lat"),
                    "lon": position.get("lon"),
                    "altitude": position.get("altitude", 0),
                    "rtk_status": position.get("rtk_status", "Unknown"),
                    "satellites": position.get("satellites", 0),
                    "hdop": position.get("hdop", 0.0),
                    "speed_knots": position.get("speed_knots"),
                    "heading": position.get("heading"),
                    "timestamp": position.get("timestamp")
                })
            else:
                return jsonify({
                    "error": "No GPS position available",
                    "lat": None,
                    "lon": None,
                    "rtk_status": rtk_manager.rtk_status if hasattr(rtk_manager, 'rtk_status') else "No Fix",
                    "satellites": 0,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }), 200
                
        except RTKAppError as e:
            logger.error(f"RTK position error: {e}")
            return jsonify({"error": str(e)}), 503
        except Exception as e:
            logger.error(f"Unexpected error in position API: {e}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
    
    @app.route('/api/track')
    def api_track():
        """Get current track data with error handling"""
        try:
            rtk_manager = app_manager.get_rtk_manager()
            
            if not rtk_manager:
                return jsonify({
                    "error": "RTK system not initialized",
                    "session_id": "",
                    "points": []
                }), 503
            
            track_data = rtk_manager.get_track_data()
            return jsonify(track_data)
            
        except Exception as e:
            logger.error(f"Error in track API: {e}", exc_info=True)
            return jsonify({
                "error": "Failed to retrieve track data",
                "session_id": "",
                "points": []
            }), 500
    
    @app.route('/api/status')
    def api_status():
        """Get RTK system status with comprehensive diagnostics"""
        try:
            rtk_manager = app_manager.get_rtk_manager()
            
            if not rtk_manager:
                return jsonify({
                    "rtk_status": "System Unavailable",
                    "running": False,
                    "ntrip_connected": False,
                    "gps_connected": False,
                    "satellites": 0,
                    "hdop": 0.0,
                    "last_update": None,
                    "system_mode": "Offline",
                    "rtk_fix_available": False,
                    "rtk_fix_status": "RTK-FIX Unavailable",
                    "rtk_fix_color": "red",
                    "error": "RTK system not initialized"
                }), 503
            
            status = rtk_manager.get_status()
            
            # Add current position info and additional details
            position = rtk_manager.get_current_position()
            if position:
                status.update({
                    "satellites": position.get("satellites", 0),
                    "hdop": position.get("hdop", 0.0),
                    "last_update": position.get("timestamp"),
                    "accuracy_status": position.get("rtk_status", "Unknown")
                })
            else:
                status.update({
                    "satellites": 0,
                    "hdop": 0.0,
                    "last_update": None,
                    "accuracy_status": "No Fix"
                })
            
            # Add system mode description with enhanced logic
            ntrip_connected = status.get("ntrip_connected", False)
            gps_connected = status.get("gps_connected", False)
            
            # Add RTK-FIX status based on NTRIP connection
            status["rtk_fix_available"] = ntrip_connected
            status["rtk_fix_status"] = "RTK-FIX Available" if ntrip_connected else "RTK-FIX Unavailable"
            status["rtk_fix_color"] = "green" if ntrip_connected else "red"
            
            if ntrip_connected and gps_connected:
                status["system_mode"] = "RTK Mode"
            elif gps_connected:
                status["system_mode"] = "GPS Only"
            else:
                status["system_mode"] = "Offline"
            
            return jsonify(status)
            
        except Exception as e:
            logger.error(f"Error in status API: {e}", exc_info=True)
            return jsonify({
                "error": "Failed to retrieve system status",
                "rtk_status": "Error",
                "running": False
            }), 500
    
    @app.route('/api/health')
    def api_health():
        """Health check endpoint for monitoring"""
        try:
            rtk_manager = app_manager.get_rtk_manager()
            
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "rtk_system": "available" if rtk_manager else "unavailable",
                "components": {
                    "flask_app": "running",
                    "rtk_manager": "running" if rtk_manager and rtk_manager.running else "stopped",
                    "gps_connection": "connected" if rtk_manager and hasattr(rtk_manager, 'system') and rtk_manager.system and hasattr(rtk_manager.system, 'gps') and rtk_manager.system.gps.is_connected() else "disconnected",
                    "ntrip_connection": "connected" if rtk_manager and hasattr(rtk_manager, 'system') and rtk_manager.system and hasattr(rtk_manager.system, 'ntrip_service') and rtk_manager.system.ntrip_service and rtk_manager.system.ntrip_service.is_connected() else "disconnected"
                }
            }
            
            # Determine overall health
            if not rtk_manager:
                health_status["status"] = "degraded"
                health_status["message"] = "RTK system not available"
            elif not rtk_manager.running:
                health_status["status"] = "unhealthy"
                health_status["message"] = "RTK system not running"
            
            status_code = 200 if health_status["status"] == "healthy" else 503
            return jsonify(health_status), status_code
            
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return jsonify({
                "status": "unhealthy",
                "error": "Health check failed",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }), 500
    
    
    @app.route('/api/tracks')
    def api_tracks():
        """Get list of available track files"""
        try:
            rtk_manager = app_manager.get_rtk_manager()
            
            if not rtk_manager:
                return jsonify({
                    "error": "RTK system not initialized",
                    "tracks": []
                }), 503
            
            # This would need track_logger functionality
            # For now return current session only
            track_data = rtk_manager.get_track_data()
            return jsonify({
                "current_session": track_data["session_id"],
                "tracks": [datetime.now().strftime("%Y%m%d")]  # Today's date
            })
            
        except Exception as e:
            logger.error(f"Error in tracks API: {e}", exc_info=True)
            return jsonify({
                "error": "Failed to retrieve tracks",
                "tracks": []
            }), 500

def get_rtk_manager():
    """Get global RTK manager instance - deprecated, use app_manager instead"""
    logger.warning("get_rtk_manager() is  deprecated, use app_manager.get_rtk_manager() instead")
    return app_manager.get_rtk_manager()
