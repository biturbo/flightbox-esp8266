#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#import logging
#logging.basicConfig(level=logging.DEBUG)

import BMP280 as BMP280

#sensor = BMP280(mode=BMP280_OSAMPLE_16)
sensor = BMP280.BMP280()


degrees = sensor.read_temperature()
pascals = sensor.read_pressure()
hectopascals = pascals / 100
meter = sensor.read_altitude()

print('Temp      = {0:0.3f} deg C'.format(degrees))
print('Pressure  = {0:0.2f} hPa'.format(hectopascals))
print('Altitude  = {0:0.2f} m'.format(meter))

