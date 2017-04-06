# Copyright (c) 2014 Adafruit Industries
import logging
import time



class BMP280(object):
	# BMP280 default address.
	I2CADDR = 0x76
	BME280_CONFIG = 0x60
	
	# Operating Modes
	OSAMPLE_1 = 1
	OSAMPLE_2 = 2
	OSAMPLE_4 = 3
	OSAMPLE_8 = 4
	OSAMPLE_16 = 5
	
	# BMP280 Registers
	
	REGISTER_DIG_T1 = 0x88  # Trimming parameter registers
	REGISTER_DIG_T2 = 0x8A
	REGISTER_DIG_T3 = 0x8C
	
	REGISTER_DIG_P1 = 0x8E
	REGISTER_DIG_P2 = 0x90
	REGISTER_DIG_P3 = 0x92
	REGISTER_DIG_P4 = 0x94
	REGISTER_DIG_P5 = 0x96
	REGISTER_DIG_P6 = 0x98
	REGISTER_DIG_P7 = 0x9A
	REGISTER_DIG_P8 = 0x9C
	REGISTER_DIG_P9 = 0x9E
	
	REGISTER_DIG_H1 = 0xA1
	REGISTER_DIG_H2 = 0xE1
	REGISTER_DIG_H3 = 0xE3
	REGISTER_DIG_H4 = 0xE4
	REGISTER_DIG_H5 = 0xE5
	REGISTER_DIG_H6 = 0xE6
	REGISTER_DIG_H7 = 0xE7
	
	REGISTER_CHIPID = 0xD0
	REGISTER_VERSION = 0xD1
	REGISTER_SOFTRESET = 0xE0
	
	REGISTER_CONTROL_HUM = 0xF2
	REGISTER_CONTROL = 0xF4
	REGISTER_CONFIG = 0xF5
	REGISTER_PRESSURE_DATA = 0xF7
	REGISTER_TEMP_DATA = 0xFA
	BME280_REGISTER_HUMIDITY_DATA = 0xFD


	def __init__(self, mode=OSAMPLE_1, address=I2CADDR, i2c=None,**kwargs):
		self._logger = logging.getLogger('Turbo_I2C.BMP280')
		# Check that mode is valid.
		if mode not in [BMP280.OSAMPLE_1, BMP280.OSAMPLE_2, BMP280.OSAMPLE_4,
						BMP280.OSAMPLE_8, BMP280.OSAMPLE_16]:
			raise ValueError(
				'Unexpected mode value {0}.  Set mode to one of BMP280.ULTRALOWPOWER, BMP280.STANDARD, BMP280.HIGHRES, or BMP280.ULTRAHIGHRES'.format(mode))
		self._mode = mode
		# Create I2C device.
		if i2c is None:
			import Adafruit_GPIO.I2C as I2C
			i2c = I2C
		self._device = i2c.get_i2c_device(address, **kwargs)
		# Load calibration values.
		self._load_calibration()
		self._device.write8(BMP280.REGISTER_CONTROL, 0x3F)
		self.t_fine = 0.0
		self.ChipID = self._device.readU8(BMP280.REGISTER_CHIPID)
		self.HasHumidity = (self.ChipID & BMP280.BME280_CONFIG ) == BMP280.BME280_CONFIG 
		self._logger.debug('ChipID = 0x{0:2x}'.format(self.ChipID))
		self.Version = self._device.readU8(BMP280.REGISTER_VERSION )
		self._logger.debug('Version = 0x{0:2x}'.format(self.Version ))

	def _load_calibration(self):
		self.dig_T1 = self._device.readU16LE(BMP280.REGISTER_DIG_T1)
		self.dig_T2 = self._device.readS16LE(BMP280.REGISTER_DIG_T2)
		self.dig_T3 = self._device.readS16LE(BMP280.REGISTER_DIG_T3)
		self.dig_P1 = self._device.readU16LE(BMP280.REGISTER_DIG_P1)
		self.dig_P2 = self._device.readS16LE(BMP280.REGISTER_DIG_P2)
		self.dig_P3 = self._device.readS16LE(BMP280.REGISTER_DIG_P3)
		self.dig_P4 = self._device.readS16LE(BMP280.REGISTER_DIG_P4)
		self.dig_P5 = self._device.readS16LE(BMP280.REGISTER_DIG_P5)
		self.dig_P6 = self._device.readS16LE(BMP280.REGISTER_DIG_P6)
		self.dig_P7 = self._device.readS16LE(BMP280.REGISTER_DIG_P7)
		self.dig_P8 = self._device.readS16LE(BMP280.REGISTER_DIG_P8)
		self.dig_P9 = self._device.readS16LE(BMP280.REGISTER_DIG_P9)
		self.dig_H1 = self._device.readU8(BMP280.REGISTER_DIG_H1)
		self.dig_H2 = self._device.readS16LE(BMP280.REGISTER_DIG_H2)
		self.dig_H3 = self._device.readU8(BMP280.REGISTER_DIG_H3)
		self.dig_H6 = self._device.readS8(BMP280.REGISTER_DIG_H7)

		h4 = self._device.readS8(BMP280.REGISTER_DIG_H4)
		h4 = (h4 << 24) >> 20
		self.dig_H4 = h4 | (self._device.readU8(BMP280.REGISTER_DIG_H5) & 0x0F)

		h5 = self._device.readS8(BMP280.REGISTER_DIG_H6)
		h5 = (h5 << 24) >> 20
		self.dig_H5 = h5 | (self._device.readU8(BMP280.REGISTER_DIG_H5) >> 4 & 0x0F)

		self._logger.debug('T1 = {0:6d}'.format(self.dig_T1))
		self._logger.debug('T2 = {0:6d}'.format(self.dig_T2))
		self._logger.debug('T3 = {0:6d}'.format(self.dig_T3))
		self._logger.debug('P1 = {0:6d}'.format(self.dig_P1))
		self._logger.debug('P2 = {0:6d}'.format(self.dig_P2))
		self._logger.debug('P3 = {0:6d}'.format(self.dig_P3))
		self._logger.debug('P4 = {0:6d}'.format(self.dig_P4))
		self._logger.debug('P5 = {0:6d}'.format(self.dig_P5))
		self._logger.debug('P6 = {0:6d}'.format(self.dig_P6))
		self._logger.debug('P7 = {0:6d}'.format(self.dig_P7))
		self._logger.debug('P8 = {0:6d}'.format(self.dig_P8))
		self._logger.debug('P9 = {0:6d}'.format(self.dig_P9))
		self._logger.debug('H1 = {0:6d}'.format(self.dig_H1))
		self._logger.debug('H2 = {0:6d}'.format(self.dig_H2))
		self._logger.debug('H3 = {0:6d}'.format(self.dig_H3))
		self._logger.debug('H4 = {0:6d}'.format(self.dig_H4))
		self._logger.debug('H5 = {0:6d}'.format(self.dig_H5))
		self._logger.debug('H6 = {0:6d}'.format(self.dig_H6))


	def read_raw_temp(self):
		"""Reads the raw (uncompensated) temperature from the sensor."""
		meas = self._mode
		self._device.write8(BMP280.REGISTER_CONTROL_HUM, meas)
		meas = self._mode << 5 | self._mode << 2 | 1
		self._device.write8(BMP280.REGISTER_CONTROL, meas)
		sleep_time = 0.00125 + 0.0023 * (1 << self._mode)
		sleep_time = sleep_time + 0.0023 * (1 << self._mode) + 0.000575
		sleep_time = sleep_time + 0.0023 * (1 << self._mode) + 0.000575
		time.sleep(sleep_time)  # Wait the required time
		msb = self._device.readU8(BMP280.REGISTER_TEMP_DATA)
		lsb = self._device.readU8(BMP280.REGISTER_TEMP_DATA + 1)
		xlsb = self._device.readU8(BMP280.REGISTER_TEMP_DATA + 2)
		raw = ((msb << 16) | (lsb << 8) | xlsb) >> 4
		return raw

	def read_raw_pressure(self):
		"""Reads the raw (uncompensated) pressure level from the sensor."""
		"""Assumes that the temperature has already been read """
		"""i.e. that enough delay has been provided"""
		msb = self._device.readU8(BMP280.REGISTER_PRESSURE_DATA)
		lsb = self._device.readU8(BMP280.REGISTER_PRESSURE_DATA + 1)
		xlsb = self._device.readU8(BMP280.REGISTER_PRESSURE_DATA + 2)
		raw = ((msb << 16) | (lsb << 8) | xlsb) >> 4
		return raw

	def read_raw_humidity(self):
		"""Assumes that the temperature has already been read """
		"""i.e. that enough delay has been provided"""
		msb = self._device.readU8(BMP280.BME280_REGISTER_HUMIDITY_DATA)
		lsb = self._device.readU8(BMP280.BME280_REGISTER_HUMIDITY_DATA + 1)
		raw = (msb << 8) | lsb
		return raw

	def read_temperature(self):
		"""Gets the compensated temperature in degrees celsius."""
		# float in Python is double precision
		UT = float(self.read_raw_temp())
		var1 = (UT / 16384.0 - self.dig_T1 / 1024.0) * float(self.dig_T2)
		var2 = ((UT / 131072.0 - self.dig_T1 / 8192.0) * (
		UT / 131072.0 - self.dig_T1 / 8192.0)) * float(self.dig_T3)
		self.t_fine = int(var1 + var2)
		temp = (var1 + var2) / 5120.0
		return temp

	def read_pressure(self):
		"""Gets the compensated pressure in Pascals."""
		adc = self.read_raw_pressure()
		var1 = self.t_fine / 2.0 - 64000.0
		var2 = var1 * var1 * self.dig_P6 / 32768.0
		var2 = var2 + var1 * self.dig_P5 * 2.0
		var2 = var2 / 4.0 + self.dig_P4 * 65536.0
		var1 = (self.dig_P3 * var1 * var1 / 524288.0 + self.dig_P2 * var1) / 524288.0
		var1 = (1.0 + var1 / 32768.0) * self.dig_P1
		if var1 == 0:
			return 0
		p = 1048576.0 - adc
		p = ((p - var2 / 4096.0) * 6250.0) / var1
		var1 = self.dig_P9 * p * p / 2147483648.0
		var2 = p * self.dig_P8 / 32768.0
		p = p + (var1 + var2 + self.dig_P7) / 16.0
		return p

	def read_humidity(self):
		if self.HasHumidity:
			adc = self.read_raw_humidity()
			h = self.t_fine - 76800.0
			h = (adc - (self.dig_H4 * 64.0 + self.dig_H5 / 16384.8 * h)) * (
			self.dig_H2 / 65536.0 * (1.0 + self.dig_H6 / 67108864.0 * h * (
			1.0 + self.dig_H3 / 67108864.0 * h)))
			h = h * (1.0 - self.dig_H1 * h / 524288.0)
			if h > 100:
				h = 100
			elif h < 0:
				h = 0
			return h
		else:
			return null

	def read_altitude(self, sealevel_pa=101325.0):
		"""Calculates the altitude in meters."""
		# Calculation taken straight from section 3.6 of the datasheet.
		pressure = float(self.read_pressure())
		altitude = 44330.0 * (1.0 - pow(pressure / sealevel_pa, (1.0/5.255)))
		self._logger.debug('Altitude {0} m'.format(altitude))
		return altitude

	def read_sealevel_pressure(self, altitude_m=0.0):
		"""Calculates the pressure at sealevel when given a known altitude in
		meters. Returns a value in Pascals."""
		pressure = float(self.read_pressure())
		p0 = pressure / pow(1.0 - altitude_m/44330.0, 5.255)
		self._logger.debug('Sealevel pressure {0} Pa'.format(p0))
		return p0
