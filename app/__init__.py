"""
Flask application for RTK Mower
Provides web interface and API endpoints for GPS tracking
"""

from flask import Flask, jsonify, render_template
from datetime import datetime
import logging
import threading
import time
from gps.rtk_manager import RTKManager

# Global RTK manager instance
rtk_manager = None
rtk_thread = None

def create_app():
    """Flask application factory"""
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    app.config['SECRET_KEY'] = 'rtk-mower-secret-key'
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize RTK system
    _init_rtk_system()
    
    # Register routes
    _register_routes(app)
    
    return app

def _init_rtk_system():
    """Initialize RTK system in background thread"""
    global rtk_manager, rtk_thread
    
    def rtk_worker():
        global rtk_manager
        rtk_manager = RTKManager()
        
        if rtk_manager.initialize():
            logging.info("RTK Manager initialized successfully")
            
            if rtk_manager.start():
                logging.info("RTK system started successfully")
            else:
                logging.error("Failed to start RTK system")
        else:
            logging.error("Failed to initialize RTK Manager")
    
    rtk_thread = threading.Thread(target=rtk_worker, daemon=True)
    rtk_thread.start()

def _register_routes(app):
    """Register Flask routes"""
    
    @app.route('/')
    def index():
        """Main page with map"""
        return render_template('map.html')
    
    @app.route('/api/position')
    def api_position():
        """Get current GPS position"""
        if not rtk_manager:
            return jsonify({
                "error": "RTK system not initialized",
                "lat": None,
                "lon": None,
                "rtk_status": "Disconnected",
                "satellites": 0,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }), 503
        
        position = rtk_manager.get_current_position()
        
        if position:
            return jsonify({
                "lat": position.lat,
                "lon": position.lon,
                "altitude": position.altitude,
                "rtk_status": position.rtk_status,
                "satellites": position.satellites,
                "hdop": position.hdop,
                "speed_knots": position.speed_knots,
                "heading": position.heading,
                "timestamp": position.timestamp
            })
        else:
            return jsonify({
                "error": "No GPS position available",
                "lat": None,
                "lon": None,
                "rtk_status": "No Fix",
                "satellites": 0,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }), 404
    
    @app.route('/api/track')
    def api_track():
        """Get current track data"""
        if not rtk_manager:
            return jsonify({
                "error": "RTK system not initialized",
                "session_id": "",
                "points": []
            }), 503
        
        track_data = rtk_manager.get_track_data()
        return jsonify(track_data)
    
    @app.route('/api/status')
    def api_status():
        """Get RTK system status"""
        if not rtk_manager:
            return jsonify({
                "rtk_status": "Disconnected",
                "running": False,
                "ntrip_connected": False,
                "gps_connected": False,
                "error": "RTK system not initialized"
            }), 503
        
        status = rtk_manager.get_status()
        
        # Add current position info
        position = rtk_manager.get_current_position()
        if position:
            status.update({
                "satellites": position.satellites,
                "hdop": position.hdop,
                "last_update": position.timestamp
            })
        else:
            status.update({
                "satellites": 0,
                "hdop": 0.0,
                "last_update": None
            })
        
        return jsonify(status)
    
    @app.route('/api/tracks')
    def api_tracks():
        """Get list of available track files"""
        if not rtk_manager or not rtk_manager.nmea_parser:
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

def get_rtk_manager():
    """Get global RTK manager instance"""
    return rtk_manager
