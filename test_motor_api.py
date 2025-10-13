#!/usr/bin/env python3
"""
Motor Control Test Script
Tests all motor control endpoints

Usage:
    python test_motor_api.py                    # localhost:5002
    python test_motor_api.py 192.168.1.42       # custom host
    python test_motor_api.py 192.168.1.42:5002  # custom host:port
"""
import requests
import time
import sys

# Parse command line arguments
if len(sys.argv) > 1:
    host_arg = sys.argv[1]
    if '://' in host_arg:
        BASE_URL = host_arg
    elif ':' in host_arg:
        BASE_URL = f"http://{host_arg}"
    else:
        BASE_URL = f"http://{host_arg}:5002"
else:
    BASE_URL = "http://localhost:5002"

print(f"🎯 Target: {BASE_URL}")
print()

def test_endpoint(name, method, endpoint, data=None):
    """Test single endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"Endpoint: {method} {endpoint}")
    if data:
        print(f"Data: {data}")
    print('-'*60)
    
    try:
        if method == 'GET':
            response = requests.get(f"{BASE_URL}{endpoint}")
        elif method == 'POST':
            response = requests.post(
                f"{BASE_URL}{endpoint}",
                json=data,
                headers={'Content-Type': 'application/json'}
            )
        elif method == 'DELETE':
            response = requests.delete(f"{BASE_URL}{endpoint}")
        
        print(f"Status: {response.status_code}")
        result = response.json()
        print(f"Response: {result}")
        
        return result.get('success', False) or response.status_code == 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("🚀 RTK Rover - Motor Control API Test")
    print("="*60)
    
    # Test 1: Check rover availability
    if not test_endpoint("Rover System Test", "GET", "/api/rover/test"):
        print("\n❌ Rover system not available. Make sure the app is running.")
        sys.exit(1)
    
    print("\n✅ Rover system is available")
    
    # Test 2: Motor status
    test_endpoint("Motor Status", "GET", "/api/motor/status")
    
    # Test 3: Forward
    print("\n⏳ Testing FORWARD (2 seconds)...")
    test_endpoint("Forward", "POST", "/api/motor/forward", {"speed": 0.3})
    time.sleep(2)
    
    # Test 4: Stop
    test_endpoint("Stop", "POST", "/api/motor/stop")
    time.sleep(1)
    
    # Test 5: Backward
    print("\n⏳ Testing BACKWARD (2 seconds)...")
    test_endpoint("Backward", "POST", "/api/motor/backward", {"speed": 0.3})
    time.sleep(2)
    
    # Test 6: Stop
    test_endpoint("Stop", "POST", "/api/motor/stop")
    time.sleep(1)
    
    # Test 7: Turn Left
    print("\n⏳ Testing TURN LEFT (2 seconds)...")
    test_endpoint("Turn Left", "POST", "/api/motor/left", {"turn": 0.4})
    time.sleep(2)
    
    # Test 8: Stop
    test_endpoint("Stop", "POST", "/api/motor/stop")
    time.sleep(1)
    
    # Test 9: Turn Right
    print("\n⏳ Testing TURN RIGHT (2 seconds)...")
    test_endpoint("Turn Right", "POST", "/api/motor/right", {"turn": 0.4})
    time.sleep(2)
    
    # Test 10: Stop
    test_endpoint("Stop", "POST", "/api/motor/stop")
    time.sleep(1)
    
    # Test 11: Manual Move (Speed + Turn)
    print("\n⏳ Testing MANUAL MOVE (forward with slight right turn, 2 seconds)...")
    test_endpoint("Manual Move", "POST", "/api/motor/move", {"speed": 0.4, "turn": 0.2})
    time.sleep(2)
    
    # Test 12: Stop
    test_endpoint("Stop", "POST", "/api/motor/stop")
    time.sleep(1)
    
    # Test 13: Differential Drive
    print("\n⏳ Testing DIFFERENTIAL DRIVE (left faster = turn right, 2 seconds)...")
    test_endpoint("Differential Drive", "POST", "/api/motor/drive", {"left": 0.5, "right": 0.3})
    time.sleep(2)
    
    # Test 14: Stop
    test_endpoint("Stop", "POST", "/api/motor/stop")
    time.sleep(1)
    
    # Test 15: Set speed limit
    test_endpoint("Set Max Speed", "POST", "/api/motor/speed", {"speed": 0.6})
    
    # Final status check
    test_endpoint("Final Motor Status", "GET", "/api/motor/status")
    
    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        print("Stopping motors...")
        try:
            requests.post(f"{BASE_URL}/api/motor/stop")
        except:
            pass
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("Stopping motors...")
        try:
            requests.post(f"{BASE_URL}/api/motor/stop")
        except:
            pass
        sys.exit(1)
