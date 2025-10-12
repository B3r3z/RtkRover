#!/usr/bin/env python3
"""
Test Integration Script
Testuje integrację RoverManager z RTKManager
"""
import sys
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test 1: Sprawdź czy wszystkie moduły są dostępne"""
    logger.info("=" * 60)
    logger.info("TEST 1: Sprawdzanie importów")
    logger.info("=" * 60)
    
    try:
        from gps.rtk_manager import RTKManager
        logger.info("✅ RTKManager import OK")
    except ImportError as e:
        logger.error(f"❌ RTKManager import FAILED: {e}")
        return False
    
    try:
        from rover_manager_singleton import global_rover_manager
        logger.info("✅ GlobalRoverManager import OK")
    except ImportError as e:
        logger.error(f"❌ GlobalRoverManager import FAILED: {e}")
        return False
    
    try:
        from navigation.navigator import Navigator
        logger.info("✅ Navigator import OK")
    except ImportError as e:
        logger.error(f"❌ Navigator import FAILED: {e}")
        return False
    
    try:
        from motor_control.motor_controller import MotorController
        logger.info("✅ MotorController import OK")
    except ImportError as e:
        logger.error(f"❌ MotorController import FAILED: {e}")
        return False
    
    logger.info("✅ Wszystkie importy OK\n")
    return True


def test_position_dataclass():
    """Test 2: Sprawdź rozszerzoną strukturę Position"""
    logger.info("=" * 60)
    logger.info("TEST 2: Sprawdzanie Position dataclass")
    logger.info("=" * 60)
    
    try:
        from gps.core.interfaces import Position, RTKStatus
        
        # Utworzenie Position z nowymi polami
        pos = Position(
            lat=52.2297,
            lon=21.0122,
            altitude=100.0,
            satellites=12,
            hdop=0.8,
            rtk_status=RTKStatus.RTK_FIXED,
            timestamp="2025-10-12T12:00:00",
            speed=5.5,      # NOWE
            heading=45.0    # NOWE
        )
        
        logger.info(f"Position created: lat={pos.lat}, lon={pos.lon}")
        logger.info(f"Speed: {pos.speed} knots")
        logger.info(f"Heading: {pos.heading}°")
        logger.info("✅ Position dataclass OK\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Position dataclass FAILED: {e}")
        return False


def test_rover_manager_singleton():
    """Test 3: Test singleton initialization (bez RTK)"""
    logger.info("=" * 60)
    logger.info("TEST 3: GlobalRoverManager Singleton")
    logger.info("=" * 60)
    
    try:
        from rover_manager_singleton import global_rover_manager
        
        # Test singleton
        instance1 = global_rover_manager
        instance2 = global_rover_manager
        
        if instance1 is instance2:
            logger.info("✅ Singleton pattern działa")
        else:
            logger.error("❌ Singleton pattern NIE działa")
            return False
        
        # Test status bez inicjalizacji
        status = global_rover_manager.get_status()
        logger.info(f"Status (niezainicjalizowany): {status}")
        
        if not status['initialized']:
            logger.info("✅ Status niezainicjalizowanego managera OK\n")
            return True
        else:
            logger.error("❌ Manager nie powinien być zainicjalizowany")
            return False
            
    except Exception as e:
        logger.error(f"❌ GlobalRoverManager test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_navigation_algorithms():
    """Test 4: Test algorytmów nawigacyjnych"""
    logger.info("=" * 60)
    logger.info("TEST 4: Algorytmy nawigacyjne")
    logger.info("=" * 60)
    
    try:
        from navigation.algorithms.geo_utils import GeoUtils
        
        # Test Haversine
        warsaw = (52.2297, 21.0122)
        krakow = (50.0647, 19.9450)
        
        distance = GeoUtils.haversine_distance(
            warsaw[0], warsaw[1],
            krakow[0], krakow[1]
        )
        
        logger.info(f"Dystans Warszawa-Kraków: {distance:.0f}m ({distance/1000:.1f}km)")
        
        # Test bearing
        bearing = GeoUtils.calculate_bearing(
            warsaw[0], warsaw[1],
            krakow[0], krakow[1]
        )
        
        logger.info(f"Kurs Warszawa→Kraków: {bearing:.1f}°")
        
        # Validate results
        if 250000 < distance < 300000:  # ~250-300km
            logger.info("✅ Haversine calculation OK")
        else:
            logger.error(f"❌ Haversine seems wrong: {distance}m")
            return False
        
        if 180 < bearing < 200:  # Roughly south
            logger.info("✅ Bearing calculation OK")
        else:
            logger.error(f"❌ Bearing seems wrong: {bearing}°")
            return False
        
        logger.info("✅ Algorytmy nawigacyjne OK\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Navigation algorithms test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_motor_controller_simulation():
    """Test 5: Motor controller w trybie symulacji"""
    logger.info("=" * 60)
    logger.info("TEST 5: Motor Controller (simulation mode)")
    logger.info("=" * 60)
    
    try:
        from motor_control.motor_controller import MotorController
        from motor_control.drivers.l298n_driver import L298NDriver
        from navigation.core.data_types import NavigationCommand
        from datetime import datetime
        
        # Initialize in simulation mode
        driver = L298NDriver(
            gpio_pins={
                'left': {'in1': 17, 'in2': 22, 'enable': 12},
                'right': {'in1': 23, 'in2': 24, 'enable': 13}
            },
            use_gpio=False  # Simulation mode
        )
        
        controller = MotorController(
            motor_driver=driver,
            max_speed=0.5,
            safety_timeout=5.0
        )
        
        # Start controller
        if not controller.start():
            logger.error("❌ Failed to start motor controller")
            return False
        
        logger.info("✅ Motor controller started in simulation mode")
        
        # Test commands
        logger.info("Testing forward movement...")
        cmd = NavigationCommand(speed=0.5, turn_rate=0.0, timestamp=datetime.now())
        controller.execute_navigation_command(cmd)
        time.sleep(0.5)
        
        logger.info("Testing turn right...")
        cmd = NavigationCommand(speed=0.3, turn_rate=0.5, timestamp=datetime.now())
        controller.execute_navigation_command(cmd)
        time.sleep(0.5)
        
        logger.info("Testing emergency stop...")
        controller.emergency_stop()
        time.sleep(0.5)
        
        # Get status
        status = controller.get_status()
        logger.info(f"Controller status: running={status['is_running']}")
        
        # Stop
        controller.stop()
        logger.info("✅ Motor controller test OK\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Motor controller test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_integration_simulation():
    """Test 6: Pełna integracja w trybie symulacji (bez hardware)"""
    logger.info("=" * 60)
    logger.info("TEST 6: Pełna integracja (symulacja)")
    logger.info("=" * 60)
    
    try:
        from rover_manager_singleton import global_rover_manager
        from navigation.core.data_types import Waypoint
        
        # Note: Tego testu nie można wykonać bez prawdziwego RTK managera
        # Ale możemy sprawdzić czy struktura jest OK
        
        logger.info("Sprawdzanie struktury waypoint...")
        wp = Waypoint(lat=52.2297, lon=21.0122, name="Test Point")
        logger.info(f"Waypoint: {wp.name} at ({wp.lat:.4f}, {wp.lon:.4f})")
        logger.info(f"Tolerance: {wp.tolerance}m")
        
        logger.info("✅ Struktura integracji OK")
        logger.info("ℹ️  Pełny test wymaga uruchomionego RTK managera\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Integration test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Uruchom wszystkie testy"""
    logger.info("\n" + "=" * 60)
    logger.info("INTEGRATION TEST SUITE")
    logger.info("Testing RoverManager ↔ RTKManager Integration")
    logger.info("=" * 60 + "\n")
    
    tests = [
        ("Imports", test_imports),
        ("Position Dataclass", test_position_dataclass),
        ("RoverManager Singleton", test_rover_manager_singleton),
        ("Navigation Algorithms", test_navigation_algorithms),
        ("Motor Controller", test_motor_controller_simulation),
        ("Full Integration", test_full_integration_simulation),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info("=" * 60)
    logger.info(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED!")
        return 0
    else:
        logger.error(f"❌ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
