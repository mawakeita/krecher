from gpiozero import LED, Device
from gpiozero.pins.lgpio import LGPIOFactory
from time import sleep

Device.pin_factory = LGPIOFactory(chip=15)

led = LED(21)
led.on()
print("LED on")
sleep(3)
led.off()
print("LED off")
