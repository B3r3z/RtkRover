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

try:
    while True:
        # 1) Obie pary kół jadą do przodu
        print("Sekwencja: oba silniki do przodu")
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH)
        GPIO.output(IN4, GPIO.LOW)
        pwm.ChangeDutyCycle(50)
        pwm_b.ChangeDutyCycle(50)
        sleep(2)

        # 2) Obie pary kół jadą do tyłu
        print("Sekwencja: oba silniki do tyłu")
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH)
        pwm.ChangeDutyCycle(80)
        pwm_b.ChangeDutyCycle(80)
        sleep(2)

        # 3) Skręcanie: lewy do przodu, prawy do tyłu
        print("Sekwencja: skręcanie (lewy do przodu, prawy do tyłu)")
        GPIO.output(IN1, GPIO.HIGH)  # silnik A do przodu
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.LOW)   # silnik B do tyłu
        GPIO.output(IN4, GPIO.HIGH)
        pwm.ChangeDutyCycle(60)
        pwm_b.ChangeDutyCycle(60)
        sleep(2)

except KeyboardInterrupt:
    pass

# Sprzątanie
pwm.stop()
GPIO.cleanup()
