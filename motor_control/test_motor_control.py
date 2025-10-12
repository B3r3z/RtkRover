import RPi.GPIO as GPIO
from time import sleep

# Numery GPIO (BCM)
IN1 = 17
IN2 = 22
ENA = 12

IN3 = 23
IN4 = 24
ENB = 13

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)
GPIO.setup(ENA, GPIO.OUT)
GPIO.setup(IN3, GPIO.OUT)
GPIO.setup(IN4, GPIO.OUT)
GPIO.setup(ENB, GPIO.OUT)

# Ustawienie PWM na pinie ENA z częstotliwością 1000 Hz
pwm = GPIO.PWM(ENA, 1000)
pwm.start(0)  # start z duty cycle 0%
# PWM dla drugiego silnika na ENB
pwm_b = GPIO.PWM(ENB, 1000)
pwm_b.start(0)
# Ustaw domyślnie kierunki na LOW (żeby silniki były zatrzymane)
GPIO.output(IN1, GPIO.LOW)
GPIO.output(IN2, GPIO.LOW)
GPIO.output(IN3, GPIO.LOW)
GPIO.output(IN4, GPIO.LOW)

# Czy powtarzać sekwencję w loopie czy wykonać jednokrotnie (ułatwia debug)
RUN_LOOP = False

# Krótkie opóźnienie przed zmianą duty cycle
sleep(0.05)

try:
    def run_sequences_once():
        # 1) Obie pary kół jadą do przodu
        print("Sekwencja: oba silniki do przodu")
        print(f"Pins: IN1={IN1}, IN2={IN2}, ENA={ENA}; IN3={IN3}, IN4={IN4}, ENB={ENB}")
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH)
        GPIO.output(IN4, GPIO.LOW)
        # najpierw ustaw kierunek, krótkie opóźnienie, potem duty
        sleep(0.05)
        pwm.ChangeDutyCycle(70)
        pwm_b.ChangeDutyCycle(70)
        print("Duty A=70, Duty B=70")
        sleep(2)

        # 2) Obie pary kół jadą do tyłu
        print("Sekwencja: oba silniki do tyłu")
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH)
        sleep(0.05)
        pwm.ChangeDutyCycle(70)
        pwm_b.ChangeDutyCycle(70)
        print("Duty A=70, Duty B=70")
        sleep(2)

        # 3) Skręcanie: lewy do przodu, prawy do tyłu
        print("Sekwencja: skręcanie (lewy do przodu, prawy do tyłu)")
        GPIO.output(IN1, GPIO.HIGH)  # silnik A do przodu
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.LOW)   # silnik B do tyłu
        GPIO.output(IN4, GPIO.HIGH)
        sleep(0.05)
        pwm.ChangeDutyCycle(60)
        pwm_b.ChangeDutyCycle(60)
        print("Duty A=60, Duty B=60")
        sleep(2)

    if RUN_LOOP:
        while True:
            run_sequences_once()
    else:
        # Najpierw testuj każdy silnik osobno żeby wykluczyć okablowanie/ zasilanie
        def test_individual_motors():
            print("--- Test silnika A (IN1/IN2, ENA) ---")
            GPIO.output(IN1, GPIO.HIGH)
            GPIO.output(IN2, GPIO.LOW)
            sleep(0.05)
            for d in (0, 20, 40, 60, 80, 100):
                pwm.ChangeDutyCycle(d)
                print(f"A duty={d}, IN1={GPIO.input(IN1)}, IN2={GPIO.input(IN2)}")
                sleep(0.3)
            pwm.ChangeDutyCycle(0)
            GPIO.output(IN1, GPIO.LOW)
            GPIO.output(IN2, GPIO.LOW)

            print("--- Test silnika B (IN3/IN4, ENB) ---")
            GPIO.output(IN3, GPIO.HIGH)
            GPIO.output(IN4, GPIO.LOW)
            sleep(0.05)
            for d in (0, 20, 40, 60, 80, 100):
                pwm_b.ChangeDutyCycle(d)
                print(f"B duty={d}, IN3={GPIO.input(IN3)}, IN4={GPIO.input(IN4)}")
                sleep(0.3)
            pwm_b.ChangeDutyCycle(0)
            GPIO.output(IN3, GPIO.LOW)
            GPIO.output(IN4, GPIO.LOW)

        test_individual_motors()
        run_sequences_once()

except KeyboardInterrupt:
    pass

# Sprzątanie
pwm.stop()
GPIO.cleanup()
