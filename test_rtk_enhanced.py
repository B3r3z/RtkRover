#!/usr/bin/env python3
"""
Test diagnostyczny z rekomendacjami poprawy sygnału RTK
"""

import sys
import os
import logging
import time
import statistics

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps.rtk_manager import RTKManager

def test_rtk_diagnostics():
    """Test diagnostyczny z rekomendacjami poprawy RTK"""
    
    print("🔧 Test diagnostyczny RTK z poprawkami kodu")
    print("=" * 70)
    print("🆕 Nowe funkcje:")
    print("   - Adaptacyjny timing GGA (8-20s w zależności od jakości)")
    print("   - Monitoring RTCM data flow")
    print("   - Automatyczne ostrzeżenia o jakości sygnału")
    print("   - Rozszerzona diagnostyka RTK readiness")
    print()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    rtk = RTKManager()
    
    # Enhanced tracking
    measurements = []
    rtk_events = []
    
    def position_callback(pos_data):
        lat = pos_data['lat']
        lon = pos_data['lon']
        status = pos_data['rtk_status']
        sats = pos_data.get('satellites', 0)
        hdop = pos_data.get('hdop', 0.0)
        
        # Store measurement for analysis
        measurements.append({
            'timestamp': time.time(),
            'hdop': hdop,
            'satellites': sats,
            'rtk_status': status,
            'lat': lat,
            'lon': lon
        })
        
        # Track RTK status changes
        if len(measurements) > 1:
            prev_status = measurements[-2]['rtk_status']
            if status != prev_status:
                rtk_events.append({
                    'time': time.time(),
                    'from': prev_status,
                    'to': status,
                    'hdop': hdop,
                    'satellites': sats
                })
                print(f"🔄 RTK Status change: {prev_status} → {status}")
        
        # Quality indicator
        if hdop <= 2.0:
            hdop_indicator = "🟢"
        elif hdop <= 5.0:
            hdop_indicator = "🟡"
        else:
            hdop_indicator = "🔴"
            
        quality = assess_signal_quality(sats, hdop)
        print(f"📍 {lat:.6f}, {lon:.6f} | {status:<10} | Sats: {sats:2d} | {hdop_indicator}HDOP: {hdop:4.1f} | {quality}")
    
    rtk.set_position_callback(position_callback)
    
    try:
        print("🔄 Inicjalizacja RTK Manager...")
        if rtk.initialize():
            print("✅ RTK Manager zainicjalizowany")
            
            print("🔄 Uruchomienie RTK system...")
            if rtk.start():
                print("✅ RTK system uruchomiony")
                
                # Enhanced status check
                status = rtk.get_status()
                print(f"📊 Status systemu:")
                print(f"   GPS połączony: {status['gps_connected']}")
                print(f"   NTRIP połączony: {status['ntrip_connected']}")
                print(f"   Signal quality: {status.get('signal_quality', 'Unknown')}")
                print(f"   RTK ready: {status.get('rtk_ready', False)}")
                if not status.get('rtk_ready', False):
                    print(f"   Reason: {status.get('rtk_ready_reason', 'Unknown')}")
                print()
                
                if status['gps_connected']:
                    print("🛰️  GPS połączony! Enhanced monitoring przez 90 sekund...")
                    print("🔧 Nowe funkcje aktywne:")
                    print("   - Adaptacyjny GGA timing")
                    print("   - RTCM data monitoring")
                    print("   - Signal quality warnings")
                    print()
                    print("📍 Format: LAT, LON | STATUS | Satelity | HDOP | Quality")
                    print("-" * 70)
                    
                    # Monitor for 90 seconds
                    start_time = time.time()
                    
                    while time.time() - start_time < 90:
                        time.sleep(1)
                    
                    # Enhanced analysis
                    print("\n" + "=" * 70)
                    print("📊 ROZSZERZONA ANALIZA RTK:")
                    print("=" * 70)
                    
                    if measurements:
                        # HDOP analysis
                        hdop_values = [m['hdop'] for m in measurements if m['hdop'] > 0]
                        if hdop_values:
                            avg_hdop = statistics.mean(hdop_values)
                            min_hdop = min(hdop_values)
                            max_hdop = max(hdop_values)
                            
                            print(f"📈 HDOP Analysis:")
                            print(f"   Średni: {avg_hdop:.2f}")
                            print(f"   Najlepszy: {min_hdop:.2f}")
                            print(f"   Najgorszy: {max_hdop:.2f}")
                            
                            # Trend analysis
                            if len(hdop_values) > 10:
                                first_half = hdop_values[:len(hdop_values)//2]
                                second_half = hdop_values[len(hdop_values)//2:]
                                trend = statistics.mean(second_half) - statistics.mean(first_half)
                                
                                if abs(trend) > 0.5:
                                    trend_text = "poprawia się" if trend < 0 else "pogarsza się"
                                    print(f"   Trend: HDOP {trend_text} ({trend:+.2f})")
                        
                        # Satellite analysis
                        sat_counts = [m['satellites'] for m in measurements if m['satellites'] > 0]
                        if sat_counts:
                            avg_sats = statistics.mean(sat_counts)
                            min_sats = min(sat_counts)
                            max_sats = max(sat_counts)
                            
                            print(f"\n🛰️  Satellite Analysis:")
                            print(f"   Średnia: {avg_sats:.1f}")
                            print(f"   Minimum: {min_sats}")
                            print(f"   Maximum: {max_sats}")
                        
                        # RTK status distribution
                        status_counts = {}
                        for m in measurements:
                            status = m['rtk_status']
                            status_counts[status] = status_counts.get(status, 0) + 1
                        
                        print(f"\n📡 RTK Status Distribution:")
                        for status, count in status_counts.items():
                            percentage = (count / len(measurements)) * 100
                            print(f"   {status}: {percentage:.1f}% ({count}/{len(measurements)})")
                        
                        # RTK events analysis
                        if rtk_events:
                            print(f"\n🔄 RTK Status Changes: {len(rtk_events)}")
                            for event in rtk_events[-3:]:  # Show last 3 changes
                                elapsed = event['time'] - start_time
                                print(f"   {elapsed:.0f}s: {event['from']} → {event['to']} (HDOP: {event['hdop']:.1f})")
                    
                    # Enhanced recommendations
                    print(f"\n💡 ROZSZERZONE REKOMENDACJE:")
                    provide_enhanced_recommendations(measurements, rtk_events, status)
                        
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
    """Enhanced signal quality assessment"""
    if satellites >= 12 and hdop <= 1.5:
        return "🟢 Excellent"
    elif satellites >= 10 and hdop <= 2.0:
        return "🟢 Very Good"
    elif satellites >= 8 and hdop <= 3.0:
        return "🟡 Good"
    elif satellites >= 6 and hdop <= 5.0:
        return "🟠 Fair"
    else:
        return "🔴 Poor"

def provide_enhanced_recommendations(measurements, rtk_events, status):
    """Provide detailed recommendations based on analysis"""
    
    if not measurements:
        print("   ❌ Brak danych do analizy")
        return
    
    avg_hdop = statistics.mean([m['hdop'] for m in measurements if m['hdop'] > 0])
    avg_sats = statistics.mean([m['satellites'] for m in measurements if m['satellites'] > 0])
    
    print(f"\n🎯 PRIORITIZED ACTION PLAN:")
    
    # Critical issues first
    if avg_hdop > 5.0:
        print(f"   🚨 CRITICAL: HDOP = {avg_hdop:.1f} - RTK Fixed impossible")
        print(f"      1. RELOCATE antenna to open area (no buildings/trees within 50m)")
        print(f"      2. CHECK antenna is perfectly horizontal")
        print(f"      3. MOVE away from metal structures (cars, fences)")
        print(f"      4. WAIT for better satellite geometry (try again in 30min)")
    
    elif avg_hdop > 2.0:
        print(f"   ⚠️  MAJOR: HDOP = {avg_hdop:.1f} - RTK Float possible, Fixed unlikely")
        print(f"      1. CHECK antenna position (clear 360° view above 15° elevation)")
        print(f"      2. WAIT 10-15 minutes for satellite constellation changes")
        print(f"      3. VERIFY no interference sources nearby (WiFi, metal)")
    
    else:
        print(f"   ✅ HDOP = {avg_hdop:.1f} - Good for RTK!")
    
    # Satellite issues
    if avg_sats < 8:
        print(f"   📡 Satellite count low: {avg_sats:.1f} - need ≥8 for reliable RTK")
        print(f"      1. CHECK for obstructions (buildings, trees)")
        print(f"      2. MOVE to higher elevation if possible")
        print(f"      3. WAIT - more satellites may become visible")
    
    # NTRIP issues
    if not status.get('ntrip_connected', False):
        print(f"   🌐 NTRIP disconnected - no RTK corrections")
        print(f"      1. CHECK internet connection")
        print(f"      2. VERIFY ASG-EUPOS credentials")
        print(f"      3. TRY different mounting point")
    
    # RTK status analysis
    has_rtk_fixed = any(m['rtk_status'] == 'RTK Fixed' for m in measurements)
    has_rtk_float = any(m['rtk_status'] == 'RTK Float' for m in measurements)
    
    if not has_rtk_fixed and not has_rtk_float:
        if avg_hdop <= 2.0 and avg_sats >= 8:
            print(f"   🔍 Good signal but no RTK - possible causes:")
            print(f"      1. NTRIP corrections not reaching GPS")
            print(f"      2. GPS needs more time for RTK convergence (wait 5-10min)")
            print(f"      3. Base station too far (>50km from ASG-EUPOS)")
    
    # Time-based recommendations
    print(f"\n⏰ TIMING RECOMMENDATIONS:")
    print(f"   - RTK convergence: Usually 30s-5min after good signal")
    print(f"   - Satellite geometry: Changes every 10-15 minutes")
    print(f"   - Best times: Avoid early morning/late evening")
    print(f"   - Weather: Clear sky optimal, heavy clouds reduce signal")
    
    # Hardware recommendations
    print(f"\n🔧 HARDWARE CHECKLIST:")
    print(f"   ☐ Antenna mounted horizontally (use spirit level)")
    print(f"   ☐ Clear view 360° above 15° elevation")
    print(f"   ☐ >5m from metal objects (cars, buildings)")
    print(f"   ☐ >2m above ground level")
    print(f"   ☐ Stable mounting (no vibration)")
    print(f"   ☐ Good cable connections (check for corrosion)")

if __name__ == "__main__":
    test_rtk_diagnostics()
