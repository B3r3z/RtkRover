import RPi.GPIO as GPIO
from time import sleep

# Numery GPIO (BCM)
IN1 = 17
IN2 = 22
ENA = 12

GPIO.setmode(GPIO.BCM)
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)
GPIO.setup(ENA, GPIO.OUT)

# Ustawienie PWM na pinie ENA z częstotliwością 1000 Hz
pwm = GPIO.PWM(ENA, 1000)
pwm.start(0)  # start z duty cycle 0%

try:
    while True:
        # Obrót do przodu
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        pwm.ChangeDutyCycle(80)  # prędkość 80/100
        sleep(2)

        # Obrót do tyłu
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH)
        pwm.ChangeDutyCycle(80)
        sleep(2)

except KeyboardInterrupt:
    pass

# Sprzątanie
pwm.stop()
GPIO.cleanup()
