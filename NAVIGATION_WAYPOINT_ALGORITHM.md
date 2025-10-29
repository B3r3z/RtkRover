# Algorytm Nawigacji Podążania Po Trasie (Way-Point Navigation Algorithm)

## Spis Treści
1. [Przegląd Systemu](#przegląd-systemu)
2. [Architektura](#architektura)
3. [Maszyna Stanów Nawigacji](#maszyna-stanów-nawigacji)
4. [Zarządzanie Kolejką Way-Pointów](#zarządzanie-kolejką-way-pointów)
5. [Obsługa Błędów](#obsługa-błędów)
6. [Pseudokod](#pseudokod)
7. [Diagram Przepływu](#diagram-przepływu)
8. [Typowe Przypadki Użycia](#typowe-przypadki-użycia)

---

## Przegląd Systemu

System nawigacji RTK Rover implementuje zaawansowany algorytm podążania po trasie składającej się z sekwencji punktów nawigacyjnych (way-pointów). Algorytm wykorzystuje:

- **GPS-RTK**: Precyzyjne pozycjonowanie (dokładność 2-3 cm) przez ASG-EUPOS NTRIP
- **VTG (Velocity Track Ground)**: Dane o kursie i prędkości z GPS
- **Maszynę stanów 4-fazową**: CALIBRATING → ALIGNING → DRIVING → REACHED
- **Kolejkę FIFO**: Zarządzanie wieloma punktami docelowymi
- **Regulator PID**: Płynna kontrola kursu

### Kluczowe Cechy

✅ **Odporność na błędy danych GPS**
- Automatyczna kalibracja kursu początkowego
- Wykrywanie starych danych GPS (timeout 2s)
- Fallback przy braku danych VTG

✅ **Obsługa wielu punktów**
- Automatyczne przechodzenie do kolejnego way-pointu
- Możliwość dodawania punktów w locie
- Monitoring pozostałych punktów w trasie

✅ **Bezpieczeństwo**
- Emergency stop (ESC key + button)
- Timeout monitoring w każdej fazie
- Graceful degradation przy błędach

---

## Architektura

### Komponenty Systemu

```
┌─────────────────────────────────────────────────────────────┐
│                      RoverManager                            │
│                  (Główny Koordynator)                        │
└───────────────┬─────────────────────────────┬───────────────┘
                │                              │
        ┌───────▼──────┐              ┌───────▼──────────┐
        │  RTK Manager │              │    Navigator     │
        │  (GPS Data)  │              │  (Nawigacja)     │
        └──────┬───────┘              └────────┬─────────┘
               │                               │
               │ Position,                     │ Navigation
               │ Heading,                      │ Command
               │ Speed (VTG)                   │
               │                               │
               └───────────────┬───────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Motor Controller   │
                    │  (Sterowanie L298N) │
                    └─────────────────────┘
```

### Struktura Danych

#### Waypoint
```python
@dataclass
class Waypoint:
    lat: float              # Szerokość geograficzna
    lon: float              # Długość geograficzna
    name: Optional[str]     # Nazwa punktu (opcjonalna)
    altitude: Optional[float]
    tolerance: float = 0.01  # Promień osiągnięcia (metry)
    speed_limit: Optional[float]
    timestamp: datetime
```

#### NavigationCommand
```python
@dataclass
class NavigationCommand:
    speed: float        # -1.0 do 1.0 (ujemny = cofanie)
    turn_rate: float    # -1.0 do 1.0 (ujemny = lewo, dodatni = prawo)
    timestamp: datetime
    priority: int = 0   # Wyższy priorytet nadpisuje niższy
```

---

## Maszyna Stanów Nawigacji

Algorytm wykorzystuje maszynę stanów 4-fazową dla precyzyjnej kontroli:

```
     START
       ↓
   [IDLE]
       ↓
       ├─(brak kursu GPS)─→ [CALIBRATING] ──(kurs uzyskany)──┐
       │                          ↓                           │
       │                    (timeout/fail)                    │
       ↓                          ↓                           │
  [ALIGNING] ←──────────────────────────────────────────────┘
       ↓
  (kurs poprawny)
       ↓
  [DRIVING] ────(błąd kursu > 30°)────→ [ALIGNING]
       ↓              ↑
  (dystans < tol)     │
       ↓              │
  [REACHED] ──────────┘
       ↓
  (następny waypoint lub IDLE)
```

### Faza 1: CALIBRATING (Kalibracja Kursu)

**Cel**: Uzyskanie wiarygodnego odczytu kursu z GPS VTG

**Warunki aktywacji**:
- Brak dostępnego kursu GPS (`heading = None`)
- Pierwszy raz po uruchomieniu
- Po stracie sygnału VTG

**Działanie**:
1. Robot porusza się prosto z prędkością 50% (0.5)
2. Zbiera próbki kursu z VTG (min. 3 próbki)
3. Weryfikuje spójność próbek (wariancja < 15°)
4. Po uzyskaniu spójnych danych → przejście do ALIGNING

**Parametry**:
- `calibration_duration`: 5.0s (max czas kalibracji)
- `calibration_speed`: 0.5 (50% prędkości)
- `required_samples`: 3 (min. liczba próbek)
- `variance_threshold`: 15° (max rozrzut próbek)

**Obsługa timeout**:
- Po 5s bez pełnej kalibracji → użycie dostępnych danych
- Brak próbek → przejście do DRIVING (ostateczny fallback)

**Pseudokod**:
```
FUNCTION handle_calibration():
    elapsed = time_since_calibration_start()
    
    IF current_heading IS NOT None:
        calibration_samples.append(current_heading)
        LOG("Sample #{count}: {heading}°, speed={speed} m/s")
    
    IF len(calibration_samples) >= required_samples:
        variance = max(samples) - min(samples)
        IF variance < 15.0:
            avg_heading = mean(calibration_samples)
            calibration_mode = False
            transition_to(ALIGNING)
            LOG("✅ Calibration complete: {avg_heading}°")
            RETURN None  # Signal phase change
        ELSE:
            LOG("⚠️ Inconsistent samples (variance={variance}°)")
            calibration_samples = last_2_samples(samples)
    
    ELSE IF elapsed >= calibration_duration:
        IF len(samples) > 0:
            LOG("⚠️ Calibration TIMEOUT - using partial data")
            transition_to(ALIGNING)
        ELSE:
            LOG("❌ Calibration FAILED - no samples")
            transition_to(DRIVING)  # Try anyway
        RETURN None
    
    ELSE:
        LOG("Calibrating... {elapsed}s / {duration}s")
        RETURN NavigationCommand(speed=0.5, turn_rate=0.0)
END FUNCTION
```

### Faza 2: ALIGNING (Obracanie do Celu)

**Cel**: Obrócenie robota w miejscu, aby skierować się dokładnie na cel

**Warunki aktywacji**:
- Po zakończeniu kalibracji
- Gdy błąd kursu > 30° podczas DRIVING
- Po ustawieniu nowego celu

**Działanie**:
1. Oblicz wymagany kurs do celu (bearing)
2. Oblicz różnicę między aktualnym a wymaganym kursem
3. Obracaj w miejscu (speed=0) z regulowaną prędkością obrotu
4. Gdy błąd < 15° → przejście do DRIVING

**Parametry**:
- `align_tolerance`: 15° (próg błędu dla przejścia do DRIVING)
- `align_speed`: 0.4 (40% max prędkości obrotu)
- `align_timeout`: 10s (max czas obracania)

**Obsługa błędów**:
- Brak kursu → przejście do DRIVING (jazda w miarę prosto)
- Timeout 10s → przejście do DRIVING mimo błędu

**Pseudokod**:
```
FUNCTION handle_align_phase():
    bearing_to_target = calculate_bearing(current_pos, target_pos)
    
    IF current_heading IS None:
        LOG("⚠️ No heading during ALIGN, switching to DRIVE")
        transition_to(DRIVING)
        RETURN NavigationCommand(speed=0.5, turn_rate=0.0)
    
    heading_error = angle_difference(current_heading, bearing_to_target)
    
    IF abs(heading_error) < align_tolerance:
        LOG("✅ Aligned! Error: {error}°")
        transition_to(DRIVING)
        reset_pid()
        RETURN NavigationCommand(speed=max_speed, turn_rate=0.0)
    
    elapsed = time_since_phase_start()
    IF elapsed > align_timeout:
        LOG("⏱️ ALIGN timeout, switching to DRIVE anyway")
        transition_to(DRIVING)
        RETURN NavigationCommand(speed=0.5, turn_rate=0.0)
    
    # Continue rotating in place
    turn_direction = 1.0 IF heading_error > 0 ELSE -1.0
    turn_intensity = min(abs(heading_error) / 90.0, 1.0)
    
    EVERY 2 seconds:
        LOG("Aligning: current={current}°, target={bearing}°, error={error}°")
    
    RETURN NavigationCommand(
        speed=0.0,  # Don't move forward
        turn_rate=turn_direction * turn_intensity * align_speed
    )
END FUNCTION
```

### Faza 3: DRIVING (Jazda do Celu)

**Cel**: Poruszanie się do przodu w kierunku celu z małymi korektami kursu

**Warunki aktywacji**:
- Po osiągnięciu prawidłowego kursu w ALIGNING
- Po timeout kalibracji (fallback)

**Działanie**:
1. Jedź z maksymalną prędkością
2. Monitoruj odległość do celu
3. Stosuj małe korekty kursu (P-controller, nie pełny PID)
4. Gdy odległość < tolerance → przejście do REACHED
5. Gdy błąd kursu > 30° → powrót do ALIGNING

**Parametry**:
- `max_speed`: 1.0 (100% prędkości)
- `realign_threshold`: 30° (próg powrotu do ALIGNING)
- `drive_correction_gain`: 0.02 (wzmocnienie korektora P)
- `correction_limit`: ±0.2 (max korekta obrotu)

**Korekta kursu**:
```python
correction = heading_error * drive_correction_gain
correction = clamp(correction, -0.2, 0.2)
```

**Obsługa błędów**:
- Brak kursu → jazda prosto z 50% prędkości
- Duży błąd kursu (>30°) → powrót do ALIGNING

**Pseudokod**:
```
FUNCTION handle_drive_phase():
    distance = calculate_distance(current_pos, target_pos)
    bearing_to_target = calculate_bearing(current_pos, target_pos)
    
    IF distance <= waypoint_tolerance:
        transition_to(REACHED)
        RETURN handle_waypoint_reached()
    
    IF current_heading IS None:
        LOG("⚠️ No heading during DRIVE, continuing straight")
        RETURN NavigationCommand(speed=0.5, turn_rate=0.0)
    
    heading_error = angle_difference(current_heading, bearing_to_target)
    
    IF abs(heading_error) > realign_threshold:
        LOG("Heading error too large ({error}°), re-aligning...")
        transition_to(ALIGNING)
        reset_pid()
        RETURN handle_align_phase()
    
    # Small proportional correction (not full PID)
    correction = heading_error * drive_correction_gain
    correction = clamp(correction, -0.2, 0.2)
    
    EVERY 2 seconds:
        LOG("Driving: dist={dist}m, heading={heading}°, error={error}°")
    
    # Log progress milestones
    IF distance > 10.0 AND not logged_10m:
        LOG("Navigating to '{name}' - Distance: {dist}m")
        logged_10m = True
    ELSE IF distance <= 5.0 AND not logged_5m:
        LOG("Approaching '{name}' - Distance: {dist}m")
        logged_5m = True
    
    RETURN NavigationCommand(
        speed=max_speed,
        turn_rate=correction
    )
END FUNCTION
```

### Faza 4: REACHED (Osiągnięto Cel)

**Cel**: Obsługa osiągnięcia waypointa i przejście do kolejnego

**Warunki aktywacji**:
- Odległość do celu < `waypoint.tolerance`

**Działanie**:
1. Zatrzymaj robota (speed=0, turn_rate=0)
2. Oznacz waypoint jako osiągnięty
3. **Tryb WAYPOINT**: Zakończ nawigację (IDLE)
4. **Tryb PATH_FOLLOWING**: Przejdź do kolejnego waypointa lub zakończ

**Pseudokod**:
```
FUNCTION handle_waypoint_reached():
    LOG("✅ Waypoint reached: '{name}' at ({lat}, {lon})")
    status = REACHED_WAYPOINT
    
    IF mode == PATH_FOLLOWING:
        IF has_next_waypoint():
            advance_to_next()
            target_waypoint = get_next_waypoint()
            status = NAVIGATING
            reset_logging_flags()
            remaining = get_remaining_count()
            LOG("Moving to next waypoint: '{name}' ({remaining} remaining)")
        ELSE:
            status = PATH_COMPLETE
            target_waypoint = None
            LOG("🏁 Path complete! All waypoints reached.")
    ELSE:
        # Single waypoint mode - stop
        target_waypoint = None
        status = IDLE
        LOG("🏁 Navigation complete - waypoint reached")
    
    reset_pid()
    navigation_phase = IDLE
    
    RETURN NavigationCommand(speed=0.0, turn_rate=0.0)
END FUNCTION
```

---

## Zarządzanie Kolejką Way-Pointów

### SimpleWaypointManager

Implementuje zarządzanie kolejką FIFO (First-In-First-Out) dla way-pointów.

**Kluczowe operacje**:

```python
class SimpleWaypointManager:
    _waypoints: List[Waypoint]  # Kolejka punktów
    _current_index: int          # Indeks aktualnego punktu
    
    # Dodaj punkt na koniec kolejki
    add_waypoint(waypoint: Waypoint)
    
    # Pobierz następny punkt bez usuwania
    get_next_waypoint() -> Optional[Waypoint]
    
    # Przejdź do kolejnego punktu
    advance_to_next() -> bool
    
    # Wyczyść wszystkie punkty
    clear_waypoints()
    
    # Pobierz wszystkie punkty
    get_all_waypoints() -> List[Waypoint]
    
    # Usuń punkt o danym indeksie
    remove_waypoint(index: int) -> bool
    
    # Liczba pozostałych punktów
    get_remaining_count() -> int
    
    # Czy są jakieś punkty?
    has_waypoints() -> bool
    
    # Reset do pierwszego punktu
    reset_to_start()
```

### Tryby Nawigacji

#### 1. WAYPOINT (Pojedynczy Punkt)
```python
navigator.set_target(waypoint)
# Nawigacja do pojedynczego punktu
# Po osiągnięciu → IDLE (stop)
```

#### 2. PATH_FOLLOWING (Ścieżka)
```python
navigator.set_waypoint_path([wp1, wp2, wp3, ...])
# Automatyczne przechodzenie przez wszystkie punkty
# Po ostatnim punkcie → PATH_COMPLETE
```

#### 3. Dodawanie punktów w locie
```python
navigator.add_waypoint(new_waypoint, auto_start=False)
# Dodaj do kolejki bez rozpoczynania nawigacji

navigator.start_navigation()
# Rozpocznij nawigację po kolejce
```

### Przykładowy przepływ PATH_FOLLOWING:

```
Waypoints: [A, B, C, D]
                    
[IDLE] ─set_waypoint_path([A,B,C,D])→ target=A ─navigate→ REACHED
                                           ↓
                                      target=B ─navigate→ REACHED
                                           ↓
                                      target=C ─navigate→ REACHED
                                           ↓
                                      target=D ─navigate→ REACHED
                                           ↓
                                     PATH_COMPLETE
```

---

## Obsługa Błędów

### 1. Brak Danych GPS

**Problem**: `current_position = None`

**Obsługa**:
```python
IF not current_position:
    error_message = "No GPS position available"
    status = ERROR
    RETURN None  # Stop navigation
```

**Akcja użytkownika**: Sprawdź połączenie GPS, NTRIP

### 2. Stare Dane GPS

**Problem**: Ostatnia pozycja starsza niż 2 sekundy

**Obsługa**:
```python
IF position_age > 2.0 seconds:
    error_message = "GPS data too old"
    status = ERROR
    LOG("GPS data is stale, stopping navigation")
    RETURN None
```

**Akcja użytkownika**: Restart GPS, sprawdź fix quality

### 3. Brak Kursu VTG

**Problem**: `current_heading = None` podczas nawigacji

**Obsługa - Strategia wielopoziomowa**:

1. **CALIBRATING**: Próba uzyskania kursu przez jazdę
2. **ALIGNING**: Przejście do DRIVING z 50% prędkością
3. **DRIVING**: Jazda prosto z 50% prędkością

```python
# Priority 1: Use GPS VTG heading
IF heading from GPS IS available:
    current_heading = GPS_heading
    
# Priority 2: Calculate from movement
ELSE IF speed > 0.5 m/s AND has_previous_position:
    current_heading = calculate_bearing(prev_pos, curr_pos)
    
# Priority 3: Keep last known heading
ELSE:
    # Keep previous heading value
    # If None, trigger CALIBRATING phase
```

### 4. Timeout w Fazie ALIGNING

**Problem**: Robot obraca się > 10s bez osiągnięcia celu

**Obsługa**:
```python
IF elapsed_in_align > align_timeout:
    LOG("ALIGN timeout, switching to DRIVE anyway")
    transition_to(DRIVING)
    speed = 0.5  # Reduced speed for safety
```

### 5. Duży Błąd Kursu podczas DRIVING

**Problem**: Robot zboczył z kursu (błąd > 30°)

**Obsługa**:
```python
IF abs(heading_error) > realign_threshold:
    LOG("Heading error too large, re-aligning...")
    transition_to(ALIGNING)
    reset_pid()
```

### 6. Brak Waypointa

**Problem**: `target_waypoint = None` ale nawigacja aktywna

**Obsługa**:
```python
IF not target_waypoint:
    status = IDLE
    RETURN NavigationCommand(speed=0.0, turn_rate=0.0)
```

### 7. Emergency Stop

**Źródła**:
- Klawisz ESC
- Przycisk hardware
- API call `/api/rover/stop`

**Obsługa**:
```python
def stop():
    is_running = False
    is_paused = False
    target_waypoint = None
    status = IDLE
    reset_pid()
    navigation_phase = IDLE
```

### Graceful Degradation

System implementuje degradację jakości działania przy błędach:

```
Pełna funkcjonalność (GPS RTK + VTG)
         ↓ (brak VTG)
GPS RTK + kurs obliczany z ruchu
         ↓ (słaby sygnał)
GPS RTK + jazda prosto z redukcją prędkości
         ↓ (brak GPS)
STOP + ERROR
```

---

## Pseudokod

### Główna Pętla Nawigacji

```
FUNCTION get_navigation_command() -> NavigationCommand:
    // Diagnostic logging
    LOG_DEBUG("running={running}, paused={paused}, pos={has_pos}, target={has_target}, heading={heading}, phase={phase}")
    
    // Pre-checks
    IF not is_running OR is_paused:
        LOG_DEBUG("Navigator not active")
        RETURN None
    
    IF not current_position:
        error_message = "No GPS position available"
        status = ERROR
        RETURN None
    
    IF is_position_stale(max_age=2.0):
        error_message = "GPS data too old"
        status = ERROR
        LOG_WARNING("GPS data is stale, stopping navigation")
        RETURN None
    
    IF not target_waypoint:
        status = IDLE
        navigation_phase = IDLE
        RETURN NavigationCommand(speed=0.0, turn_rate=0.0)
    
    // STATE MACHINE DISPATCHER
    
    // Handle CALIBRATING phase
    IF current_heading IS None AND not calibration_mode:
        calibration_mode = True
        calibration_start_time = now()
        calibration_samples = []
        navigation_phase = CALIBRATING
        LOG_WARNING("🧭 HEADING CALIBRATION STARTED")
    
    IF calibration_mode:
        command = handle_calibration()
        IF command IS None:
            // Calibration complete, re-run for next phase
            RETURN get_navigation_command()
        RETURN command
    
    // State machine router
    MATCH navigation_phase:
        CASE IDLE:
            navigation_phase = ALIGNING
            phase_start_time = now()
            LOG_INFO("Starting navigation - entering ALIGN phase")
            RETURN handle_align_phase()
        
        CASE ALIGNING:
            RETURN handle_align_phase()
        
        CASE DRIVING:
            RETURN handle_drive_phase()
        
        CASE REACHED:
            RETURN NavigationCommand(speed=0.0, turn_rate=0.0)
        
        DEFAULT:
            LOG_ERROR("Unknown navigation phase: {phase}")
            navigation_phase = ALIGNING
            phase_start_time = now()
            RETURN NavigationCommand(speed=0.0, turn_rate=0.0)
END FUNCTION
```

### Aktualizacja Pozycji

```
FUNCTION update_position(lat, lon, heading, speed):
    WITH thread_lock:
        previous_position = current_position
        current_position = (lat, lon)
        last_position_time = now()
        
        // Priority 1: Use GPS heading (VTG)
        IF heading IS NOT None:
            current_heading = heading
            LOG_DEBUG("Using GPS heading: {heading}°")
        
        // Priority 2: Calculate from movement
        ELSE IF previous_position AND speed > 0.5:
            calculated_heading = calculate_bearing(
                previous_position, current_position
            )
            current_heading = calculated_heading
            LOG_DEBUG("Calculated heading from movement: {heading}°")
        
        // Priority 3: Keep previous heading
        // (No action needed, current_heading unchanged)
        
        IF speed IS NOT None:
            current_speed = speed
        
        LOG_DEBUG("Position updated: ({lat}, {lon}), heading: {heading}, speed: {speed}")
END FUNCTION
```

### Ustawianie Celu

```
FUNCTION set_target(waypoint):
    WITH thread_lock:
        target_waypoint = waypoint
        mode = WAYPOINT
        status = NAVIGATING
        approaching_logged = False
        calibration_mode = False
        navigation_phase = IDLE
        phase_start_time = None
        
        // Reset logging flags
        reset_all_logging_flags()
        
        // Auto-start if not running
        IF not is_running:
            is_running = True
            is_paused = False
            LOG_INFO("🚀 Navigator auto-started with target")
        
        LOG_INFO("🎯 Target set: '{name}' at ({lat}, {lon})")
END FUNCTION
```

### Ustawianie Ścieżki

```
FUNCTION set_waypoint_path(waypoints):
    WITH thread_lock:
        waypoint_manager.clear_waypoints()
        
        FOR each waypoint IN waypoints:
            waypoint_manager.add_waypoint(waypoint)
        
        target_waypoint = waypoint_manager.get_next_waypoint()
        
        IF target_waypoint:
            mode = PATH_FOLLOWING
            status = NAVIGATING
            approaching_logged = False
            calibration_mode = False
            navigation_phase = IDLE
            phase_start_time = None
            
            LOG_INFO("🗺️ Path set with {count} waypoints")
            LOG_INFO("📍 Starting path - First waypoint: '{name}'")
END FUNCTION
```

---

## Diagram Przepływu

### Kompletny Diagram Maszyny Stanów

```
                    ┌─────────────────────────────────────────┐
                    │         INITIALIZATION                  │
                    │    navigator = Navigator(...)           │
                    │    set_target(waypoint) or              │
                    │    set_waypoint_path([...])             │
                    └──────────────┬──────────────────────────┘
                                   │
                                   ▼
                        ┌──────────────────┐
                        │      IDLE        │◄──────────────────┐
                        │  Waiting for     │                   │
                        │  GPS & target    │                   │
                        └────────┬─────────┘                   │
                                 │                             │
                    ┌────────────▼────────────┐                │
                    │ Check GPS & Heading     │                │
                    └────────┬────────────────┘                │
                             │                                 │
                  ┌──────────▼──────────┐                     │
                  │ Heading Available?  │                     │
                  └──┬───────────────┬──┘                     │
                     │ NO            │ YES                     │
                     │               │                         │
        ┌────────────▼──────┐        │                         │
        │   CALIBRATING     │        │                         │
        │ ┌───────────────┐ │        │                         │
        │ │Drive straight │ │        │                         │
        │ │Collect VTG    │ │        │                         │
        │ │heading samples│ │        │                         │
        │ └───────┬───────┘ │        │                         │
        │         │         │        │                         │
        │    ┌────▼─────┐   │        │                         │
        │    │ 3 samples│   │        │                         │
        │    │consistent│   │        │                         │
        │    │(var<15°)?│   │        │                         │
        │    └┬───────┬─┘   │        │                         │
        │  NO │       │ YES │        │                         │
        │  ┌──▼──┐    └─────┤        │                         │
        │  │Wait │          │        │                         │
        │  │more │          │        │                         │
        │  └──┬──┘          │        │                         │
        │     │             │        │                         │
        │  ┌──▼────────┐    │        │                         │
        │  │Timeout 5s?│    │        │                         │
        │  └──┬────┬───┘    │        │                         │
        │  NO │    │ YES    │        │                         │
        │     │    └────────┤        │                         │
        │     └─────────────┘        │                         │
        └────────────┬───────────────┘                         │
                     │                                         │
                     ▼                                         │
        ┌────────────────────────┐                            │
        │      ALIGNING          │◄───────────────┐            │
        │ ┌────────────────────┐ │                │            │
        │ │Rotate in place     │ │                │            │
        │ │speed = 0.0         │ │                │            │
        │ │turn_rate = f(error)│ │                │            │
        │ └──────────┬─────────┘ │                │            │
        │            │           │                │            │
        │    ┌───────▼────────┐  │                │            │
        │    │Heading error   │  │                │            │
        │    │< tolerance?    │  │                │            │
        │    │   (15°)        │  │                │            │
        │    └┬───────────┬───┘  │                │            │
        │  NO │           │ YES  │                │            │
        │  ┌──▼─────┐     └──────┤                │            │
        │  │Timeout?│            │                │            │
        │  │ (10s)  │            │                │            │
        │  └┬───┬───┘            │                │            │
        │NO │   │ YES            │                │            │
        │   │   └────────────────┤                │            │
        │   └────────────────────┘                │            │
        └─────────────┬──────────────────────────┘            │
                      │                                        │
                      ▼                                        │
        ┌─────────────────────────────┐                       │
        │         DRIVING             │                       │
        │ ┌─────────────────────────┐ │                       │
        │ │Drive forward           │ │                       │
        │ │speed = max_speed       │ │                       │
        │ │turn_rate = correction  │ │                       │
        │ └────────┬────────────────┘ │                       │
        │          │                  │                       │
        │   ┌──────▼────────┐         │                       │
        │   │Distance check │         │                       │
        │   └──┬─────────┬──┘         │                       │
        │      │         │            │                       │
        │   ┌──▼──┐   ┌──▼────────┐   │                       │
        │   │dist │   │Heading    │   │                       │
        │   │< tol│   │error > 30°│   │                       │
        │   └──┬──┘   └──┬────────┘   │                       │
        │   YES│      YES│            │                       │
        │      │         └────────────┼───────────────────────┘
        │      │                      │
        └──────┼──────────────────────┘
               │
               ▼
        ┌──────────────┐
        │   REACHED    │
        │ ┌──────────┐ │
        │ │Stop robot│ │
        │ │speed = 0 │ │
        │ └────┬─────┘ │
        │      │       │
        │  ┌───▼─────┐ │
        │  │  Mode?  │ │
        │  └┬───────┬┘ │
        │   │       │  │
        │PATH│    WAYPOINT
        │   │       │  │
        │ ┌─▼──┐  ┌─▼──┐
        │ │Next│  │End │
        │ │WP? │  │Nav │
        │ └─┬──┘  └─┬──┘
        │YES│   NO  │  │
        │   │   │   │  │
        └───┼───┼───┼──┘
            │   │   │
            │   │   └──────────────────────────────────────────┐
            │   └──────────────────────────────────────────────┤
            └──────────────────────────────────────────────────┤
                                                                │
                                                                ▼
                                                        ┌───────────────┐
                                                        │ IDLE / PATH   │
                                                        │  COMPLETE     │
                                                        └───────────────┘
```

### Diagram Interakcji Komponentów

```
┌─────────────┐
│ GPS Module  │ VTG data (heading, speed)
│  (LC29H)    │ GGA data (position, fix)
└──────┬──────┘
       │
       │ NMEA sentences
       │ via UART
       │
       ▼
┌──────────────────┐
│   RTK Manager    │ Parse & validate
│  (GPS Handler)   │ NTRIP corrections
└────────┬─────────┘
         │
         │ Position update:
         │ lat, lon, heading, speed
         │
         ▼
┌─────────────────────────┐
│      Navigator          │
│  ┌───────────────────┐  │
│  │ State Machine     │  │
│  │ - CALIBRATING     │  │
│  │ - ALIGNING        │  │
│  │ - DRIVING         │  │
│  │ - REACHED         │  │
│  └─────────┬─────────┘  │
│            │            │
│  ┌─────────▼─────────┐  │
│  │ Waypoint Manager  │  │
│  │ - FIFO queue      │  │
│  │ - Current target  │  │
│  └─────────┬─────────┘  │
│            │            │
│  ┌─────────▼─────────┐  │
│  │ Path Planner      │  │
│  │ - Distance calc   │  │
│  │ - Bearing calc    │  │
│  └─────────┬─────────┘  │
│            │            │
│  ┌─────────▼─────────┐  │
│  │ PID Controller    │  │
│  │ - Smooth turns    │  │
│  └─────────┬─────────┘  │
└────────────┼────────────┘
             │
             │ NavigationCommand:
             │ speed, turn_rate
             │
             ▼
┌───────────────────────┐
│  Motor Controller     │
│  ┌─────────────────┐  │
│  │ Differential    │  │
│  │ Drive Control   │  │
│  └────────┬────────┘  │
│           │           │
│  ┌────────▼────────┐  │
│  │ L298N Driver    │  │
│  │ - PWM control   │  │
│  │ - Direction     │  │
│  └────────┬────────┘  │
└───────────┼───────────┘
            │
            │ GPIO signals:
            │ ENA, IN1, IN2,
            │ ENB, IN3, IN4
            │
            ▼
    ┌───────────────┐
    │  DC Motors    │
    │  Left & Right │
    └───────────────┘
```

---

## Typowe Przypadki Użycia

### Przypadek 1: Nawigacja do Pojedynczego Punktu

**Scenariusz**: Robot ma dojechać do określonego punktu GPS.

**Kod**:
```python
from navigation.core.data_types import Waypoint

# Utwórz waypoint
target = Waypoint(
    lat=52.237049,
    lon=21.017532,
    name="Dom",
    tolerance=2.0  # 2 metry promień
)

# Rozpocznij nawigację
navigator.set_target(target)  # Auto-start
```

**Przebieg**:
1. `set_target()` ustawia cel i auto-startuje nawigację
2. Robot przechodzi przez fazy: CALIBRATING → ALIGNING → DRIVING
3. Po osiągnięciu (dystans < 2m) → REACHED → IDLE
4. Robot zatrzymuje się

**Logi**:
```
🎯 Target set: 'Dom' at (52.237049, 21.017532)
🚀 Navigator auto-started with target: Dom
🧭 HEADING CALIBRATION STARTED
✅ Heading calibration complete! Heading: 87.3°
🎯 Starting navigation - entering ALIGN phase
✅ Aligned to target! Heading: 85.1°, Target: 87.0°, Error: 1.9°
🚗 Driving: dist=45.2m, heading=85.1°, bearing=87.0°, error=1.9°
🚗 Navigating to 'Dom' - Distance: 45.2m, Bearing: 87°
...
➡️  Approaching 'Dom' - Distance: 4.8m
✅ Waypoint reached: 'Dom' at (52.237049, 21.017532)
�� Navigation complete - waypoint reached
```

### Przypadek 2: Nawigacja Po Ścieżce (Wiele Punktów)

**Scenariusz**: Robot ma przejechać trasę przez kilka punktów kontrolnych.

**Kod**:
```python
# Utwórz ścieżkę
path = [
    Waypoint(lat=52.237049, lon=21.017532, name="Start", tolerance=2.0),
    Waypoint(lat=52.238000, lon=21.018000, name="Punkt A", tolerance=2.0),
    Waypoint(lat=52.239000, lon=21.019000, name="Punkt B", tolerance=2.0),
    Waypoint(lat=52.240000, lon=21.020000, name="Meta", tolerance=2.0)
]

# Rozpocznij nawigację po ścieżce
navigator.set_waypoint_path(path)  # Auto-start
```

**Przebieg**:
1. `set_waypoint_path()` ustawia kolejkę i auto-startuje
2. Nawigacja do pierwszego punktu (Start)
3. Po osiągnięciu → automatyczne przejście do Punkt A
4. Po osiągnięciu → automatyczne przejście do Punkt B
5. Po osiągnięciu → automatyczne przejście do Meta
6. Po osiągnięciu Meta → PATH_COMPLETE

**Logi**:
```
🗺️ Path set with 4 waypoints
📍 Starting path navigation - First waypoint: 'Start'
...
✅ Waypoint reached: 'Start' at (52.237049, 21.017532)
⏭️ Advanced to waypoint #2/4: 'Punkt A'
📍 Moving to next waypoint: 'Punkt A' (3 waypoints remaining)
...
✅ Waypoint reached: 'Punkt A' at (52.238000, 21.018000)
...
✅ Waypoint reached: 'Punkt B' at (52.239000, 21.019000)
...
✅ Waypoint reached: 'Meta' at (52.240000, 21.020000)
🏁 Path complete! All waypoints reached.
```

### Przypadek 3: Dodawanie Punktów Dynamicznie

**Scenariusz**: Dodaj punkty do kolejki bez natychmiastowego startu.

**Kod**:
```python
# Dodaj punkty do kolejki
navigator.add_waypoint(Waypoint(lat=52.237049, lon=21.017532, name="WP1", tolerance=2.0))
navigator.add_waypoint(Waypoint(lat=52.238000, lon=21.018000, name="WP2", tolerance=2.0))
navigator.add_waypoint(Waypoint(lat=52.239000, lon=21.019000, name="WP3", tolerance=2.0))

# ... później ...

# Rozpocznij nawigację
navigator.start_navigation()
```

**Przebieg**:
1. `add_waypoint()` dodaje punkty do kolejki (bez startu)
2. `start_navigation()` rozpoczyna nawigację po kolejce
3. Robot przechodzi przez wszystkie punkty sekwencyjnie

### Przypadek 4: Pauza i Wznowienie

**Scenariusz**: Zatrzymaj robota w trakcie nawigacji, a później wznów.

**Kod**:
```python
# Rozpocznij nawigację
navigator.set_target(waypoint)

# ... robot jedzie ...

# Pauza (np. przeszkoda)
navigator.pause()

# ... przeszkoda usunięta ...

# Wznów
navigator.resume()
```

**Przebieg**:
1. Robot nawiguje normalnie
2. `pause()` → robot zatrzymuje się (speed=0), zachowuje cel i fazę
3. `resume()` → robot wznawia od miejsca, w którym się zatrzymał
4. Kontynuuje nawigację do celu

**Logi**:
```
🚗 Driving: dist=30.5m, ...
⏸️ Navigator paused (current target: 'Dom', phase: driving)
▶️ Navigator resumed (target: 'Dom', phase: driving)
🚗 Driving: dist=30.5m, ...
```

### Przypadek 5: Emergency Stop

**Scenariusz**: Natychmiastowe zatrzymanie robota.

**Kod**:
```python
# Zatrzymaj nawigację
navigator.stop()

# lub przez API
POST /api/rover/stop
```

**Przebieg**:
1. Robot natychmiast zatrzymuje się
2. Cel usunięty, status → IDLE
3. PID i maszyna stanów zresetowane
4. Kolejka waypoint zachowana (można wznowić przez `start_navigation()`)

### Przypadek 6: Brak Kursu VTG - Automatyczna Kalibracja

**Scenariusz**: GPS nie dostarcza kursu (VTG disabled lub słaby sygnał).

**Przebieg**:
1. Robot wykrywa `heading = None`
2. Automatyczne wejście w fazę CALIBRATING
3. Robot jedzie prosto 5s, zbierając próbki kursu
4. Po uzyskaniu spójnych danych → ALIGNING → DRIVING
5. Jeśli timeout bez danych → DRIVING z 50% prędkością (fallback)

**Logi**:
```
🧭 HEADING CALIBRATION STARTED - no GPS heading available
   Robot will drive straight for up to 5.0s at 50% speed
   Waiting for 3 consistent VTG heading samples
🧭 Heading sample #1: 87.5° (speed=0.52 m/s)
🧭 Heading sample #2: 88.1° (speed=0.54 m/s)
🧭 Heading sample #3: 87.9° (speed=0.55 m/s)
✅ Heading calibration complete! Heading: 87.8° (variance: 0.6°)
🔄 Transitioning to ALIGN phase
```

### Przypadek 7: Duże Odchylenie Kursu - Re-aligning

**Scenariusz**: Robot zboczył z kursu podczas jazdy.

**Przebieg**:
1. Robot jedzie w fazie DRIVING
2. Błąd kursu przekracza 30° (np. silny podmuch wiatru, poślizg)
3. Automatyczne przejście: DRIVING → ALIGNING
4. Robot obraca się w miejscu, aż błąd < 15°
5. Powrót do DRIVING

**Logi**:
```
🚗 Driving: dist=25.3m, heading=75.0°, bearing=110.0°, error=35.0°
🔄 Heading error too large (35.0°), re-aligning...
🔄 Phase transition: DRIVE → ALIGN
🔄 Aligning: current=75.0°, target=110.0°, error=35.0°
...
✅ Aligned to target! Heading: 108.5°, Target: 110.0°, Error: 1.5°
🔄 Phase transition: ALIGN → DRIVE
🚗 Driving: dist=25.1m, ...
```

### Przypadek 8: Monitorowanie Postępu

**Scenariusz**: Aplikacja webowa monitoruje stan nawigacji w czasie rzeczywistym.

**Kod**:
```python
# Pobierz aktualny stan
state = navigator.get_state()

# Wyświetl informacje
print(f"Pozycja: {state.current_position}")
print(f"Cel: {state.target_waypoint.name if state.target_waypoint else 'Brak'}")
print(f"Dystans: {state.distance_to_target:.1f}m")
print(f"Kurs: {state.current_heading:.1f}°")
print(f"Status: {state.status.value}")
print(f"Pozostałe punkty: {state.waypoints_remaining}")

# API endpoint
GET /api/rover/status
```

**Odpowiedź JSON**:
```json
{
  "current_position": [52.237123, 21.017654],
  "target_waypoint": {
    "lat": 52.238000,
    "lon": 21.018000,
    "name": "Punkt A",
    "tolerance": 2.0
  },
  "distance_to_target": 125.4,
  "bearing_to_target": 87.5,
  "current_heading": 85.2,
  "current_speed": 0.65,
  "mode": "path_following",
  "status": "navigating",
  "waypoints_remaining": 3,
  "error_message": null
}
```

---

## Podsumowanie

### Kluczowe Zalety Algorytmu

✅ **Odporność na błędy**
- Automatyczna kalibracja kursu
- Wykrywanie starych danych GPS
- Graceful degradation przy błędach

✅ **Precyzja**
- Maszyna stanów 4-fazowa (CALIBRATING, ALIGNING, DRIVING, REACHED)
- Osobna faza obracania (ALIGNING) vs jazdy (DRIVING)
- Małe korekty kursu podczas jazdy (P-controller)

✅ **Elastyczność**
- Tryb pojedynczego punktu (WAYPOINT)
- Tryb ścieżki (PATH_FOLLOWING)
- Dynamiczne dodawanie punktów
- Pauza/wznowienie

✅ **Bezpieczeństwo**
- Timeout w każdej fazie
- Emergency stop
- Monitoring jakości danych GPS

### Parametry Konfiguracyjne

| Parametr | Domyślna wartość | Opis |
|----------|-----------------|------|
| `max_speed` | 1.0 | Maksymalna prędkość (0.0-1.0) |
| `waypoint_tolerance` | 0.5m | Promień osiągnięcia waypointa |
| `align_tolerance` | 15° | Próg błędu dla ALIGN → DRIVE |
| `realign_threshold` | 30° | Próg błędu dla DRIVE → ALIGN |
| `align_speed` | 0.4 | Prędkość obrotu (40%) |
| `align_timeout` | 10s | Timeout fazy ALIGNING |
| `calibration_duration` | 5s | Czas kalibracji kursu |
| `calibration_speed` | 0.5 | Prędkość kalibracji (50%) |
| `drive_correction_gain` | 0.02 | Wzmocnienie korektora P |

### Wymagania Systemowe

**Hardware**:
- GPS RTK LC29H(DA) z UART
- Raspberry Pi (Zero 2 W / 4)
- L298N motor controller
- 2x DC motors

**Software**:
- Python 3.7+
- pyserial (GPS UART)
- RPi.GPIO (motor control)
- Flask (web interface)

**Sieć**:
- Połączenie internetowe (NTRIP corrections)
- ASG-EUPOS account

### Referencje

- **Implementacja**: `/navigation/navigator.py`
- **Typy danych**: `/navigation/core/data_types.py`
- **Zarządzanie kolejką**: `/navigation/waypoint_manager.py`
- **Planer ścieżki**: `/navigation/algorithms/path_planner.py`
- **Regulator PID**: `/navigation/algorithms/pid_controller.py`
- **Narzędzia geo**: `/navigation/algorithms/geo_utils.py`

---

**Wersja**: 1.0  
**Data**: 2025-10-29  
**Autor**: RTK Rover Team
