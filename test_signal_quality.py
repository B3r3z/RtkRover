#!/usr/bin/env python3
"""
Test diagnostyczny jakości sygnału GPS/RTK
"""

import sys
import os
import logging
import time
import statistics

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps.rtk_manager import RTKManager

def test_signal_quality():
    """Test diagnostyczny jakości sygnału GPS"""
    
    print("🛰️  Test diagnostyczny jakości sygnału GPS/RTK")
    print("=" * 70)
    print("🎯 Cel diagnozy:")
    print("   - Analiza HDOP (cel: <2.0 dla RTK Fixed)")
    print("   - Monitoring liczby satelitów")
    print("   - Ocena stabilności sygnału")
    print("   - Rekomendacje dla poprawy RTK")
    print()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    rtk = RTKManager()
    
    # Signal quality tracking
    hdop_values = []
    satellite_counts = []
    rtk_statuses = []
    signal_quality_log = []
    
    def position_callback(pos_data):
        lat = pos_data['lat']
        lon = pos_data['lon']
        status = pos_data['rtk_status']
        sats = pos_data.get('satellites', 0)
        hdop = pos_data.get('hdop', 0.0)
        
        # Store for analysis
        if hdop > 0:
            hdop_values.append(hdop)
        if sats > 0:
            satellite_counts.append(sats)
        rtk_statuses.append(status)
        
        # Assess signal quality
        quality = assess_signal_quality(sats, hdop)
        signal_quality_log.append(quality)
        
        # Color-coded output
        hdop_color = get_hdop_color(hdop)
        status_color = get_status_color(status)
        
        print(f"📍 {lat:.6f}, {lon:.6f} | {status_color}{status:<10}{reset_color} | "
              f"Sats: {sats:2d} | {hdop_color}HDOP: {hdop:4.1f}{reset_color} | "
              f"Quality: {quality}")
    
    rtk.set_position_callback(position_callback)
    
    try:
        print("🔄 Inicjalizacja RTK Manager...")
        if rtk.initialize():
            print("✅ RTK Manager zainicjalizowany")
            
            print("🔄 Uruchomienie RTK system...")
            if rtk.start():
                print("✅ RTK system uruchomiony")
                
                # Check status
                status = rtk.get_status()
                print(f"📊 Status systemu:")
                print(f"   GPS połączony: {status['gps_connected']}")
                print(f"   NTRIP połączony: {status['ntrip_connected']}")
                print()
                
                if status['gps_connected']:
                    print("🛰️  GPS połączony! Analiza jakości sygnału przez 60 sekund...")
                    print("📊 Kryteria jakości:")
                    print("   - HDOP <2.0 = Excellent/Good dla RTK")
                    print("   - HDOP 2.0-5.0 = Fair (możliwy RTK Float)")
                    print("   - HDOP >5.0 = Poor (tylko Single fix)")
                    print("   - Satelity ≥8 = Good, ≥12 = Excellent")
                    print()
                    print("📍 Format: LAT, LON | STATUS | Satelity | HDOP | Quality")
                    print("-" * 70)
                    
                    # Monitor for 60 seconds
                    start_time = time.time()
                    
                    while time.time() - start_time < 60:
                        time.sleep(1)
                    
                    # Analysis after monitoring
                    print("\n" + "=" * 70)
                    print("📊 ANALIZA JAKOŚCI SYGNAŁU:")
                    print("=" * 70)
                    
                    if hdop_values:
                        avg_hdop = statistics.mean(hdop_values)
                        min_hdop = min(hdop_values)
                        max_hdop = max(hdop_values)
                        
                        print(f"📈 HDOP Analysis:")
                        print(f"   Średni HDOP: {avg_hdop:.2f}")
                        print(f"   Najlepszy HDOP: {min_hdop:.2f}")
                        print(f"   Najgorszy HDOP: {max_hdop:.2f}")
                        
                        # HDOP recommendations
                        if avg_hdop <= 2.0:
                            print("   ✅ HDOP EXCELLENT - idealny dla RTK Fixed")
                        elif avg_hdop <= 3.0:
                            print("   ✅ HDOP GOOD - dobry dla RTK Float/Fixed")
                        elif avg_hdop <= 5.0:
                            print("   ⚠️  HDOP FAIR - możliwy RTK Float")
                        else:
                            print("   ❌ HDOP POOR - problemy z RTK")
                            
                    if satellite_counts:
                        avg_sats = statistics.mean(satellite_counts)
                        min_sats = min(satellite_counts)
                        max_sats = max(satellite_counts)
                        
                        print(f"\n🛰️  Satellite Analysis:")
                        print(f"   Średnia liczba: {avg_sats:.1f}")
                        print(f"   Minimum: {min_sats}")
                        print(f"   Maximum: {max_sats}")
                        
                        if avg_sats >= 12:
                            print("   ✅ SATELLITE COUNT EXCELLENT")
                        elif avg_sats >= 8:
                            print("   ✅ SATELLITE COUNT GOOD")
                        elif avg_sats >= 6:
                            print("   ⚠️  SATELLITE COUNT FAIR")
                        else:
                            print("   ❌ SATELLITE COUNT POOR")
                    
                    # RTK Status analysis
                    if rtk_statuses:
                        status_counts = {}
                        for status in rtk_statuses:
                            status_counts[status] = status_counts.get(status, 0) + 1
                        
                        print(f"\n📡 RTK Status Distribution:")
                        for status, count in status_counts.items():
                            percentage = (count / len(rtk_statuses)) * 100
                            print(f"   {status}: {percentage:.1f}% ({count}/{len(rtk_statuses)})")
                    
                    # Recommendations
                    print(f"\n💡 REKOMENDACJE:")
                    if avg_hdop > 5.0:
                        print("   🚫 HDOP za wysokie dla RTK - sprawdź:")
                        print("      - Położenie anteny (czy nie ma przeszkód)")
                        print("      - Czy antena jest pozioma")
                        print("      - Czy jest z dala od źródeł zakłóceń")
                        print("      - Spróbuj w innej lokalizacji")
                    elif avg_hdop > 2.0:
                        print("   ⚠️  HDOP graniczne - możliwe działania:")
                        print("      - Poczekaj na lepszą konfigurację satelitów")
                        print("      - Sprawdź czy antena ma dobry widok na niebo")
                    else:
                        print("   ✅ HDOP dobry dla RTK!")
                        
                    if len(rtk_statuses) > 0 and 'RTK Fixed' not in status_counts:
                        print("   📡 Brak RTK Fixed - możliwe przyczyny:")
                        print("      - NTRIP corrections nie docierają")
                        print("      - Za wysoki HDOP")
                        print("      - Słaba jakość sygnału satelitarnego")
                        print("      - Potrzeba więcej czasu na konwergencję")
                        
                else:
                    print("⚠️  GPS nie został połączony")
                    
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

def assess_signal_quality(satellites, hdop):
    """Assess overall signal quality"""
    if satellites >= 12 and hdop <= 2.0:
        return "🟢 Excellent"
    elif satellites >= 8 and hdop <= 3.0:
        return "🟡 Good"
    elif satellites >= 6 and hdop <= 5.0:
        return "🟠 Fair"
    else:
        return "🔴 Poor"

def get_hdop_color(hdop):
    """Get color code for HDOP value"""
    if hdop <= 2.0:
        return "\033[92m"  # Green
    elif hdop <= 5.0:
        return "\033[93m"  # Yellow
    else:
        return "\033[91m"  # Red

def get_status_color(status):
    """Get color code for RTK status"""
    if status == "RTK Fixed":
        return "\033[92m"  # Green
    elif status == "RTK Float":
        return "\033[93m"  # Yellow
    elif status == "Single":
        return "\033[94m"  # Blue
    else:
        return "\033[91m"  # Red

reset_color = "\033[0m"

if __name__ == "__main__":
    test_signal_quality()
