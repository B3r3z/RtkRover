"""
Track Logger - handles GPS track recording and management
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import threading
import time
import logging
from .nmea_parser import GPSPosition

logger = logging.getLogger(__name__)

class TrackLogger:
    """Manages GPS track logging with automatic file rotation"""
    
    def __init__(self, log_directory="logs", auto_save_interval=5.0):
        self.log_directory = log_directory
        self.auto_save_interval = auto_save_interval
        self.session_id = None
        self.track_data = {"session_id": "", "points": []}
        self.last_save_time = 0
        self.save_lock = threading.Lock()
        
        # Ensure log directory exists
        os.makedirs(self.log_directory, exist_ok=True)
        
        # Start new session
        self.start_new_session()
        
        # Start auto-save thread
        self._start_auto_save()
    
    def start_new_session(self):
        """Start new tracking session"""
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.track_data = {
            "session_id": self.session_id,
            "points": []
        }
        logger.info(f"Started new track session: {self.session_id}")
    
    def add_position(self, position: GPSPosition) -> bool:
        """Add GPS position to current track"""
        try:
            with self.save_lock:
                self.track_data["points"].append(position.to_dict())
            
            logger.debug(f"Added position: {position.lat:.6f}, {position.lon:.6f} ({position.rtk_status})")
            return True
            
        except Exception as e:
            logger.error(f"Error adding position to track: {e}")
            return False
    
    def save_track(self, force=False) -> bool:
        """Save track to file"""
        current_time = time.time()
        
        # Check if we should save (force or interval passed)
        if not force and (current_time - self.last_save_time) < self.auto_save_interval:
            return True
        
        try:
            with self.save_lock:
                if not self.track_data["points"]:
                    return True  # Nothing to save
                
                # Generate filename based on today's date
                track_filename = f"track_{datetime.now().strftime('%Y%m%d')}.json"
                track_filepath = os.path.join(self.log_directory, track_filename)
                
                # Save track data
                with open(track_filepath, 'w') as f:
                    json.dump(self.track_data, f, indent=2)
                
                self.last_save_time = current_time
                point_count = len(self.track_data["points"])
                
            logger.info(f"Saved track with {point_count} points to {track_filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving track: {e}")
            return False
    
    def get_track_data(self) -> Dict[str, Any]:
        """Get current track data (copy)"""
        with self.save_lock:
            return self.track_data.copy()
    
    def get_track_summary(self) -> Dict[str, Any]:
        """Get track summary statistics"""
        with self.save_lock:
            points = self.track_data["points"]
            
            if not points:
                return {
                    "session_id": self.session_id,
                    "point_count": 0,
                    "duration": 0,
                    "start_time": None,
                    "last_update": None
                }
            
            start_time = points[0]["timestamp"]
            last_time = points[-1]["timestamp"]
            
            # Calculate approximate duration
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                last_dt = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                duration = (last_dt - start_dt).total_seconds()
            except:
                duration = 0
            
            return {
                "session_id": self.session_id,
                "point_count": len(points),
                "duration": duration,
                "start_time": start_time,
                "last_update": last_time
            }
    
    def load_track(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Load track data for specific date (YYYYMMDD)"""
        try:
            track_filename = f"track_{date_str}.json"
            track_filepath = os.path.join(self.log_directory, track_filename)
            
            if not os.path.exists(track_filepath):
                logger.warning(f"Track file not found: {track_filepath}")
                return None
            
            with open(track_filepath, 'r') as f:
                track_data = json.load(f)
            
            logger.info(f"Loaded track with {len(track_data.get('points', []))} points from {track_filepath}")
            return track_data
            
        except Exception as e:
            logger.error(f"Error loading track: {e}")
            return None
    
    def list_available_tracks(self) -> List[str]:
        """List available track files"""
        try:
            track_files = []
            for filename in os.listdir(self.log_directory):
                if filename.startswith("track_") and filename.endswith(".json"):
                    # Extract date from filename
                    date_part = filename[6:14]  # track_YYYYMMDD.json
                    track_files.append(date_part)
            
            return sorted(track_files, reverse=True)  # Most recent first
            
        except Exception as e:
            logger.error(f"Error listing tracks: {e}")
            return []
    
    def _start_auto_save(self):
        """Start auto-save background thread"""
        def auto_save_loop():
            while True:
                try:
                    time.sleep(self.auto_save_interval)
                    self.save_track()
                except Exception as e:
                    logger.error(f"Error in auto-save loop: {e}")
        
        save_thread = threading.Thread(target=auto_save_loop, daemon=True)
        save_thread.start()
        logger.info(f"Started auto-save thread (interval: {self.auto_save_interval}s)")
    
    def cleanup_old_tracks(self, keep_days=30):
        """Remove track files older than specified days"""
        try:
            cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_date = cutoff_date.timestamp() - (keep_days * 24 * 3600)
            
            removed_count = 0
            for filename in os.listdir(self.log_directory):
                if filename.startswith("track_") and filename.endswith(".json"):
                    filepath = os.path.join(self.log_directory, filename)
                    file_time = os.path.getmtime(filepath)
                    
                    if file_time < cutoff_date:
                        os.remove(filepath)
                        removed_count += 1
                        logger.info(f"Removed old track file: {filename}")
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} old track files")
                
        except Exception as e:
            logger.error(f"Error cleaning up old tracks: {e}")

# Test function
def test_track_logger():
    """Test track logging functionality"""
    from .nmea_parser import GPSPosition
    
    logger = TrackLogger(log_directory="test_logs", auto_save_interval=1.0)
    
    print("Testing Track Logger:")
    print("=" * 40)
    
    # Simulate GPS positions
    test_positions = [
        GPSPosition(
            timestamp=datetime.utcnow().isoformat() + "Z",
            lat=52.4064,
            lon=16.9252,
            altitude=85.4,
            fix_quality=4,
            satellites=12,
            hdop=0.8
        ),
        GPSPosition(
            timestamp=datetime.utcnow().isoformat() + "Z", 
            lat=52.4065,
            lon=16.9253,
            altitude=85.5,
            fix_quality=4,
            satellites=12,
            hdop=0.8
        )
    ]
    
    # Add positions
    for pos in test_positions:
        logger.add_position(pos)
        print(f"Added position: {pos.lat}, {pos.lon}")
    
    # Show summary
    summary = logger.get_track_summary()
    print(f"Track summary: {summary}")
    
    # Force save
    logger.save_track(force=True)
    
    # List available tracks
    tracks = logger.list_available_tracks()
    print(f"Available tracks: {tracks}")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_track_logger()
