from flask import Flask, jsonify, render_template, request
from datetime import datetime
import logging
import threading
import time
import os
import atexit
import math
from gps.rtk_manager import RTKManager

logger = logging.getLogger(__name__)


def validate_coordinates(lat, lon):
    """
    Validate GPS coordinates
    
    Args:
        lat: Latitude value
        lon: Longitude value
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    # Type check
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False, "Coordinates must be numbers"
    
    # Range check
    if not (-90 <= lat <= 90):
        return False, "Latitude must be between -90 and 90"
    
    if not (-180 <= lon <= 180):
        return False, "Longitude must be between -180 and 180"
    
    # NaN/Inf check
    if math.isnan(lat) or math.isnan(lon):
        return False, "Invalid coordinate values (NaN)"
    
    if math.isinf(lat) or math.isinf(lon):
        return False, "Invalid coordinate values (Infinity)"
    
    return True, None


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

# Global rover manager (lazy initialized)
_rover_manager_instance = None
_rover_init_lock = threading.Lock()

def get_rover_manager():
    """
    Get or initialize rover manager
    Thread-safe lazy initialization
    """
    global _rover_manager_instance
    
    if _rover_manager_instance is not None:
        return _rover_manager_instance
    
    with _rover_init_lock:
        if _rover_manager_instance is not None:
            return _rover_manager_instance
        
        try:
            # Import here to avoid circular dependencies
            from rover_manager_singleton import global_rover_manager
            
            # Initialize with RTK manager
            rtk_manager = app_manager.get_rtk_manager()
            if rtk_manager:
                logger.info("Initializing Rover Manager...")
                _rover_manager_instance = global_rover_manager.initialize(rtk_manager)
                
                if _rover_manager_instance:
                    logger.info("✅ Rover Manager initialized successfully")
                else:
                    logger.warning("⚠️ Rover Manager initialization returned None")
            else:
                logger.warning("⚠️ RTK Manager not available, cannot initialize Rover")
        
        except ImportError as e:
            logger.warning(f"Rover Manager not available (modules not found): {e}")
            logger.info("This is expected if navigation/motor_control modules are not installed")
        except Exception as e:
            logger.error(f"Failed to initialize Rover Manager: {e}", exc_info=True)
    
    return _rover_manager_instance

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
    
    # Register cleanup handler
    def cleanup():
        """Cleanup on application shutdown"""
        logger.info("Application shutting down...")
        try:
            rover = get_rover_manager()
            if rover:
                from rover_manager_singleton import global_rover_manager
                global_rover_manager.shutdown()
                logger.info("Rover Manager shut down")
        except Exception as e:
            logger.error(f"Error during Rover shutdown: {e}")
    
    atexit.register(cleanup)
    
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

    # ==========================================
    # NAVIGATION & MOTOR CONTROL API
    # ==========================================
    
    @app.route('/api/rover/test')
    def api_rover_test():
        """Test rover system availability"""
        try:
            rover = get_rover_manager()
            if rover:
                status = rover.get_rover_status()
                return jsonify({
                    "status": "ok",
                    "message": "Rover system operational",
                    "rover_running": status.get('is_running', False)
                })
            return jsonify({
                "status": "unavailable",
                "message": "Rover system not initialized (navigation/motor modules may not be installed)"
            }), 503
        except Exception as e:
            logger.error(f"Rover test error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/status')
    def api_nav_status():
        """Get comprehensive navigation status"""
        try:
            rover = get_rover_manager()
            
            if not rover:
                return jsonify({
                    "error": "Rover system not initialized",
                    "is_running": False,
                    "available": False
                }), 503
            
            status = rover.get_rover_status()
            return jsonify(status)
            
        except Exception as e:
            logger.error(f"Navigation status error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/waypoint', methods=['POST'])
    def api_add_waypoint():
        """Add navigation waypoint to queue"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            lat = data.get('lat')
            lon = data.get('lon')
            name = data.get('name', f"WP_{datetime.now().strftime('%H%M%S')}")
            
            if lat is None or lon is None:
                return jsonify({"error": "lat and lon are required"}), 400
            
            # Validate and convert
            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                return jsonify({"error": "lat and lon must be valid numbers"}), 400
            
            # Validate coordinates
            valid, error = validate_coordinates(lat, lon)
            if not valid:
                return jsonify({"error": error, "success": False}), 400
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            if rover.add_waypoint(lat, lon, name):
                return jsonify({
                    "success": True,
                    "message": f"Waypoint '{name}' added to queue",
                    "waypoint": {"lat": lat, "lon": lon, "name": name}
                })
            else:
                return jsonify({"error": "Failed to add waypoint"}), 500
            
        except Exception as e:
            logger.error(f"Add waypoint error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/waypoints', methods=['GET'])
    def api_get_waypoints():
        """Get all waypoints in queue"""
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"waypoints": [], "error": "Rover not initialized"}), 503
            
            waypoints = rover.get_waypoints()
            return jsonify({"waypoints": waypoints, "count": len(waypoints)})
            
        except Exception as e:
            logger.error(f"Get waypoints error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/waypoints', methods=['DELETE'])
    def api_clear_waypoints():
        """Clear all waypoints from queue"""
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.clear_waypoints()
            return jsonify({"success": True, "message": "All waypoints cleared"})
            
        except Exception as e:
            logger.error(f"Clear waypoints error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/goto', methods=['POST'])
    def api_goto_waypoint():
        """Navigate to single waypoint (replaces queue)"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            lat = data.get('lat')
            lon = data.get('lon')
            name = data.get('name', 'Target')
            
            if lat is None or lon is None:
                return jsonify({"error": "lat and lon are required"}), 400
            
            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                return jsonify({"error": "lat and lon must be valid numbers"}), 400
            
            # Validate coordinates
            valid, error = validate_coordinates(lat, lon)
            if not valid:
                return jsonify({"error": error, "success": False}), 400
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            if rover.go_to_waypoint(lat, lon, name):
                return jsonify({
                    "success": True,
                    "message": f"Navigating to {name}",
                    "target": {"lat": lat, "lon": lon, "name": name}
                })
            else:
                return jsonify({"error": "Failed to set navigation target"}), 500
            
        except Exception as e:
            logger.error(f"Go to waypoint error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/path', methods=['POST'])
    def api_follow_path():
        """Follow path of multiple waypoints"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            waypoints = data.get('waypoints', [])
            
            if not waypoints:
                return jsonify({"error": "No waypoints provided"}), 400
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            # Convert to tuples and validate
            wp_tuples = []
            for i, wp in enumerate(waypoints):
                if not isinstance(wp, dict):
                    return jsonify({"error": f"Waypoint {i} must be an object"}), 400
                
                if 'lat' not in wp or 'lon' not in wp:
                    return jsonify({"error": f"Waypoint {i} missing lat or lon"}), 400
                
                try:
                    lat = float(wp['lat'])
                    lon = float(wp['lon'])
                except (ValueError, TypeError):
                    return jsonify({"error": f"Waypoint {i} has invalid coordinates"}), 400
                
                # Validate coordinates
                valid, error = validate_coordinates(lat, lon)
                if not valid:
                    return jsonify({
                        "error": f"Waypoint {i}: {error}",
                        "success": False
                    }), 400
                
                wp_tuples.append((lat, lon))
            
            if rover.follow_path(wp_tuples):
                return jsonify({
                    "success": True,
                    "message": f"Following path with {len(wp_tuples)} waypoints",
                    "waypoint_count": len(wp_tuples)
                })
            else:
                return jsonify({"error": "Failed to set path"}), 500
            
        except Exception as e:
            logger.error(f"Follow path error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/pause', methods=['POST'])
    def api_pause_navigation():
        """Pause navigation (motors stop, waypoints retained)"""
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.pause_navigation()
            return jsonify({"success": True, "message": "Navigation paused"})
            
        except Exception as e:
            logger.error(f"Pause navigation error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/resume', methods=['POST'])
    def api_resume_navigation():
        """Resume paused navigation"""
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.resume_navigation()
            return jsonify({"success": True, "message": "Navigation resumed"})
            
        except Exception as e:
            logger.error(f"Resume navigation error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/cancel', methods=['POST'])
    def api_cancel_navigation():
        """Cancel current navigation (clear waypoints, stop motors)"""
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.cancel_navigation()
            return jsonify({"success": True, "message": "Navigation cancelled"})
            
        except Exception as e:
            logger.error(f"Cancel navigation error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/navigation/emergency_stop', methods=['POST'])
    def api_emergency_stop():
        """EMERGENCY STOP - immediately halt all movement"""
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.emergency_stop()
            logger.warning("EMERGENCY STOP activated via API")
            return jsonify({
                "success": True, 
                "message": "EMERGENCY STOP activated - all motors stopped"
            })
            
        except Exception as e:
            logger.error(f"Emergency stop error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/speed', methods=['POST'])
    def api_set_speed():
        """Set maximum motor speed"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            speed = data.get('speed')
            
            if speed is None:
                return jsonify({"error": "speed parameter required"}), 400
            
            try:
                speed = float(speed)
                if not 0.0 <= speed <= 1.0:
                    return jsonify({"error": "speed must be between 0.0 and 1.0"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "speed must be a valid number"}), 400
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.set_max_speed(speed)
            return jsonify({
                "success": True,
                "message": f"Max speed set to {speed:.2f}",
                "speed": speed
            })
            
        except Exception as e:
            logger.error(f"Set speed error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/status')
    def api_motor_status():
        """Get motor controller status"""
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            status = rover.get_rover_status()
            motor_status = status.get('motor_control', {})
            return jsonify(motor_status)
            
        except Exception as e:
            logger.error(f"Motor status error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    # ==========================================
    # DIRECT MOTOR CONTROL API
    # ==========================================
    
    @app.route('/api/motor/drive', methods=['POST'])
    def api_motor_drive():
        """
        Direct differential drive control
        Bypasses navigation - for manual control
        
        Body: {
            "left": -1.0 to 1.0,
            "right": -1.0 to 1.0
        }
        """
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            left_speed = data.get('left')
            right_speed = data.get('right')
            
            if left_speed is None or right_speed is None:
                return jsonify({"error": "left and right speeds required"}), 400
            
            # Validate and convert
            try:
                left_speed = float(left_speed)
                right_speed = float(right_speed)
            except (ValueError, TypeError):
                return jsonify({"error": "Speeds must be valid numbers"}), 400
            
            # Validate ranges
            if not (-1.0 <= left_speed <= 1.0):
                return jsonify({"error": "left speed must be between -1.0 and 1.0"}), 400
            if not (-1.0 <= right_speed <= 1.0):
                return jsonify({"error": "right speed must be between -1.0 and 1.0"}), 400
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.manual_drive(left_speed, right_speed)
            
            return jsonify({
                "success": True,
                "message": "Motor command executed",
                "left": left_speed,
                "right": right_speed
            })
            
        except Exception as e:
            logger.error(f"Motor drive error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/move', methods=['POST'])
    def api_motor_move():
        """
        Manual movement with speed and turn
        
        Body: {
            "speed": -1.0 to 1.0 (forward/backward),
            "turn": -1.0 to 1.0 (left/right) [optional, default: 0]
        }
        """
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            speed = data.get('speed')
            turn_rate = data.get('turn', 0.0)
            
            if speed is None:
                return jsonify({"error": "speed parameter required"}), 400
            
            # Validate and convert
            try:
                speed = float(speed)
                turn_rate = float(turn_rate)
            except (ValueError, TypeError):
                return jsonify({"error": "speed and turn must be valid numbers"}), 400
            
            # Validate ranges
            if not (-1.0 <= speed <= 1.0):
                return jsonify({"error": "speed must be between -1.0 and 1.0"}), 400
            if not (-1.0 <= turn_rate <= 1.0):
                return jsonify({"error": "turn must be between -1.0 and 1.0"}), 400
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.manual_move(speed, turn_rate)
            
            return jsonify({
                "success": True,
                "message": "Movement command executed",
                "speed": speed,
                "turn": turn_rate
            })
            
        except Exception as e:
            logger.error(f"Motor move error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/stop', methods=['POST'])
    def api_motor_stop():
        """
        Stop all motors immediately
        Does NOT cancel navigation - motors will restart if navigation is active
        Use /api/navigation/emergency_stop to stop navigation AND motors
        """
        try:
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.stop_motors()
            
            return jsonify({
                "success": True,
                "message": "Motors stopped"
            })
            
        except Exception as e:
            logger.error(f"Motor stop error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/forward', methods=['POST'])
    def api_motor_forward():
        """Quick command: Move forward at specified speed"""
        try:
            data = request.get_json() or {}
            speed = float(data.get('speed', 0.5))
            speed = max(0.0, min(1.0, speed))
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.manual_move(speed, 0.0)
            return jsonify({"success": True, "message": f"Moving forward at {speed:.2f}"})
            
        except Exception as e:
            logger.error(f"Forward error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/backward', methods=['POST'])
    def api_motor_backward():
        """Quick command: Move backward at specified speed"""
        try:
            data = request.get_json() or {}
            speed = float(data.get('speed', 0.5))
            speed = max(0.0, min(1.0, speed))
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.manual_move(-speed, 0.0)
            return jsonify({"success": True, "message": f"Moving backward at {speed:.2f}"})
            
        except Exception as e:
            logger.error(f"Backward error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/left', methods=['POST'])
    def api_motor_left():
        """Quick command: Turn left (rotate in place)"""
        try:
            data = request.get_json() or {}
            turn = float(data.get('turn', 0.5))
            turn = max(0.0, min(1.0, turn))
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.manual_move(0.0, -turn)
            return jsonify({"success": True, "message": f"Turning left at {turn:.2f}"})
            
        except Exception as e:
            logger.error(f"Turn left error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/motor/right', methods=['POST'])
    def api_motor_right():
        """Quick command: Turn right (rotate in place)"""
        try:
            data = request.get_json() or {}
            turn = float(data.get('turn', 0.5))
            turn = max(0.0, min(1.0, turn))
            
            rover = get_rover_manager()
            if not rover:
                return jsonify({"error": "Rover system not initialized"}), 503
            
            rover.manual_move(0.0, turn)
            return jsonify({"success": True, "message": f"Turning right at {turn:.2f}"})
            
        except Exception as e:
            logger.error(f"Turn right error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/metrics')
    def api_metrics():
        """Get comprehensive system metrics and telemetry"""
        try:
            rover = get_rover_manager()
            
            if not rover:
                return jsonify({
                    "error": "Rover not initialized",
                    "metrics": None
                }), 503
            
            metrics = rover.metrics.to_dict()
            
            return jsonify({
                "success": True,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error getting metrics: {e}", exc_info=True)
            return jsonify({
                "error": str(e),
                "success": False
            }), 500

def get_rtk_manager():
    """Get global RTK manager instance - deprecated, use app_manager instead"""
    logger.warning("get_rtk_manager() is  deprecated, use app_manager.get_rtk_manager() instead")
    return app_manager.get_rtk_manager()
