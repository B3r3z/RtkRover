#!/usr/bin/env python3
"""
Test RTK Manager z rzeczywistym sprzętem GPS
Uruchom ten test na Raspberry Pi z podłączonym LC29H(DA)
"""

import sys
import os
import logging
import time
import threading

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps.rtk_manager import RTKManager

def test_real_gps():
    """Test RTK Manager z rzeczywistym sprzętem"""
    
    print("🛰️ Test RTK Manager z rzeczywistym GPS")
    print("=" * 60)
    print("⚠️  Ten test wymaga:")
    print("   - Raspberry Pi z LC29H(DA) HAT")
    print("   - Połączenie internetowe")
    print("   - Antena GPS na zewnątrz")
    print("   - Aktywne konto ASG-EUPOS")
    print()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    rtk = RTKManager()
    
    def position_callback(pos_data):
        lat = pos_data['lat']
        lon = pos_data['lon']
        status = pos_data['rtk_status']
        sats = pos_data.get('satellites', 0)
        hdop = pos_data.get('hdop', 0.0)
        
        print(f"📍 {lat:.6f}, {lon:.6f} | {status} | Sats: {sats} | HDOP: {hdop:.1f}")
    
    # Also track NTRIP status changes
    def monitor_ntrip_status(rtk_manager):
        """Background monitoring of NTRIP status"""
        last_ntrip_status = None
        reconnect_count = 0
        
        while rtk_manager.running:
            current_status = rtk_manager.get_status()
            ntrip_connected = current_status.get('ntrip_connected', False)
            
            if ntrip_connected != last_ntrip_status:
                if ntrip_connected:
                    if last_ntrip_status is False:
                        reconnect_count += 1
                        print(f"🔄 NTRIP Reconnect #{reconnect_count} sukces")
                elif last_ntrip_status is True:
                    print(f"⚠️  NTRIP Connection Lost - system spróbuje reconnect...")
                
                last_ntrip_status = ntrip_connected
            
            time.sleep(2)  # Check every 2 seconds
    
    rtk.set_position_callback(position_callback)
    
    try:
        print("🔄 Inicjalizacja RTK Manager...")
        if rtk.initialize():
            print("✅ RTK Manager zainicjalizowany")
            
            print("🔄 Uruchomienie RTK system...")
            if rtk.start():
                print("✅ RTK system uruchomiony")
                
                # Start background NTRIP monitoring
                monitor_thread = threading.Thread(target=monitor_ntrip_status, args=(rtk,), daemon=True)
                monitor_thread.start()
                
                # Check status
                status = rtk.get_status()
                print(f"📊 Status systemu:")
                print(f"   RTK Status: {status['rtk_status']}")
                print(f"   GPS połączony: {status['gps_connected']}")
                print(f"   NTRIP połączony: {status['ntrip_connected']}")
                print(f"   System działa: {status['running']}")
                print()
                
                if status['gps_connected']:
                    print("🎉 GPS połączony! Monitoring pozycji przez 120 sekund...")
                    print("📍 Format: LAT, LON | STATUS | Satelity | HDOP")
                    print("🔄 Monitorowanie NTRIP reconnect...")
                    print("-" * 60)
                    
                    # Monitor for 120 seconds (extended to see reconnect behavior)
                    start_time = time.time()
                    last_status = None
                    last_ntrip_status = None
                    position_count = 0
                    ntrip_reconnects = 0
                    
                    while time.time() - start_time < 120:
                        current_status = rtk.get_status()
                        
                        # Show RTK status changes
                        if current_status['rtk_status'] != last_status:
                            print(f"🔄 RTK Status zmieniony na: {current_status['rtk_status']}")
                            last_status = current_status['rtk_status']
                        
                        # Monitor NTRIP connection status
                        if current_status['ntrip_connected'] != last_ntrip_status:
                            if current_status['ntrip_connected']:
                                if last_ntrip_status is False:
                                    ntrip_reconnects += 1
                                    print(f"🔄 NTRIP reconnect #{ntrip_reconnects} - połączenie przywrócone")
                                else:
                                    print(f"🌐 NTRIP połączenie nawiązane")
                            else:
                                print(f"⚠️  NTRIP połączenie utracone")
                            last_ntrip_status = current_status['ntrip_connected']
                        
                        # Count position updates
                        current_position = rtk.get_current_position()
                        if current_position and current_position.get('lat'):
                            position_count += 1
                        
                        time.sleep(1)
                    
                    # Summary after monitoring
                    print("\n" + "=" * 60)
                    print("📊 PODSUMOWANIE TESTU:")
                    print("=" * 60)
                    print(f"⏱️  Czas monitorowania: 120 sekund")
                    print(f"📍 Odebrane pozycje: {position_count}")
                    print(f"🔄 NTRIP reconnects: {ntrip_reconnects}")
                    
                    final_status = rtk.get_status()
                    print(f"🛰️ Końcowy status RTK: {final_status['rtk_status']}")
                    print(f"🌐 NTRIP końcowy status: {'Połączony' if final_status['ntrip_connected'] else 'Rozłączony'}")
                    
                    if ntrip_reconnects > 0:
                        print(f"✅ System RTK z reconnect logic działa poprawnie!")
                        print(f"   - Wykryto {ntrip_reconnects} reconnect(s)")
                        print(f"   - System kontynuował pracę")
                    else:
                        print(f"✅ System RTK stabilny - brak potrzeby reconnect")
                    
                    if position_count > 100:  # Oczekujemy ~120 pozycji w 120 sekund
                        print(f"✅ GPS działa stabilnie - {position_count} pozycji w 120 sekund")
                    else:
                        print(f"⚠️  GPS niestabilny - tylko {position_count} pozycji w 120 sekund")
                        
                else:
                    print("⚠️  GPS nie został połączony - sprawdź:")
                    print("   1. Czy LC29H(DA) HAT jest podłączony")
                    print("   2. Czy UART jest włączony (/dev/ttyS0)")
                    print("   3. Czy antena GPS jest na zewnątrz")
                    print("   4. Uruchom: sudo dmesg | grep tty")
                    print("   5. Sprawdź: ls -la /dev/ttyS0")
                
                if status['ntrip_connected']:
                    print("🌐 NTRIP początkowo połączony - będzie monitorowany")
                else:
                    print("⚠️  NTRIP nie został połączony - sprawdź:")
                    print("   1. Połączenie internetowe")
                    print("   2. Dane logowania ASG-EUPOS w .env")
                    print("   3. Czy konto ASG-EUPOS jest aktywne")
                    print("   4. Test będzie kontynuowany - system spróbuje reconnect")
                print()
                    
            else:
                print("❌ Nie udało się uruchomić RTK system")
                
        else:
            print("❌ Nie udało się zainicjalizować RTK Manager")
            
    except KeyboardInterrupt:
        print("\n🛑 Test przerwany przez użytkownika")
        
    finally:
        print("\n🔄 Zatrzymywanie RTK system...")
        rtk.stop()
        print("✅ RTK system zatrzymany")

if __name__ == "__main__":
    test_real_gps()
