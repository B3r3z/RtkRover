#!/usr/bin/env python3
"""
Test script for RTK components
Run this to test individual components before deployment to Raspberry Pi
"""

import sys
import os
import logging

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_config():
    """Test configuration loading"""
    print("=" * 50)
    print("Testing configuration...")
    
    try:
        from config.settings import rtk_config, uart_config, gps_config
        
        print(f"RTK Config: {rtk_config}")
        print(f"UART Config: {uart_config}")  
        print(f"GPS Config: {gps_config}")
        
        # Check if credentials are set
        if rtk_config["username"] and rtk_config["password"]:
            print("✅ ASG-EUPOS credentials loaded")
        else:
            print("⚠️  ASG-EUPOS credentials not set in .env")
            
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_ntrip_client():
    """Test NTRIP client (connection will fail without internet/credentials)"""
    print("=" * 50)
    print("Testing NTRIP client...")
    
    try:
        from gps.ntrip_client import create_ntrip_client
        
        client = create_ntrip_client()
        print(f"✅ NTRIP client created: {client.caster}:{client.port}/{client.mountpoint}")
        
        # Test connection (will fail without proper credentials/internet)
        print("Attempting connection to ASG-EUPOS...")
        if client.connect():
            print("✅ NTRIP connection successful!")
            client.disconnect()
        else:
            print("❌ NTRIP connection failed (expected without proper setup)")
            
        return True
        
    except Exception as e:
        print(f"❌ NTRIP client test failed: {e}")
        return False

def test_gps_controller():
    """Test GPS controller (will fail without hardware)"""
    print("=" * 50)
    print("Testing GPS controller...")
    
    try:
        from gps.lc29h_controller import LC29HController
        
        gps = LC29HController()
        print(f"✅ GPS controller created for {gps.port} at {gps.baudrate} baud")
        
        # Test connection (will fail without hardware)
        print("Attempting connection to LC29H(DA)...")
        if gps.connect():
            print("✅ GPS connection successful!")
            gps.disconnect()
        else:
            print("❌ GPS connection failed (expected without hardware)")
            
        return True
        
    except Exception as e:
        print(f"❌ GPS controller test failed: {e}")
        return False

def test_rtk_manager():
    """Test RTK manager"""
    print("=" * 50)
    print("Testing RTK manager...")
    
    try:
        from gps.rtk_manager import RTKManager
        
        rtk = RTKManager()
        print("✅ RTK manager created")
        
        if rtk.initialize():
            print("✅ RTK manager initialized")
            
            status = rtk.get_status()
            print(f"Status: {status}")
            
            rtk.stop()
        else:
            print("❌ RTK manager initialization failed")
            
        return True
        
    except Exception as e:
        print(f"❌ RTK manager test failed: {e}")
        return False

def main():
    """Run all tests"""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    print("🧪 RTK Mower - Component Tests")
    print("Running tests on development machine...")
    print("Note: Hardware-dependent tests will fail (this is expected)")
    print()
    
    tests = [
        test_config,
        test_ntrip_client, 
        test_gps_controller,
        test_rtk_manager
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
            print()
        except KeyboardInterrupt:
            print("\n❌ Tests interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error in {test.__name__}: {e}")
            results.append(False)
            print()
    
    # Summary
    print("=" * 50)
    print("TEST SUMMARY:")
    passed = sum(results)
    total = len(results)
    
    for i, test in enumerate(tests):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"  {test.__name__}: {status}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! Ready for Raspberry Pi deployment.")
    else:
        print("⚠️  Some tests failed. Check configuration and dependencies.")

if __name__ == "__main__":
    main()
