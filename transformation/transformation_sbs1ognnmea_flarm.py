import asyncio
from concurrent.futures import ThreadPoolExecutor
from geopy.distance import vincenty
import logging
import pynmea2
import re
import setproctitle
import sys
from threading import Lock
import time
import math
import smbus
import serial
from configparser import ConfigParser

from data_hub.data_hub_item import DataHubItem
from transformation.transformation_module import TransformationModule
import utils.conversion, utils.calculation

__author__ = "Serge Guex"
__copyright__ = "Copyright 2017"
__email__ = ""

logging.basicConfig(filename='/home/pi/opt/flightbox/static/flightbox.txt',format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',level=logging.INFO)
#portOUT = serial.Serial('/dev/ttyUSB0', 19200)
parser = ConfigParser()
parser.read('/home/pi/opt/flightbox/transformation/pcasconf.ini')

@asyncio.coroutine
def input_processor(loop, data_input_queue, aircraft, aircraft_lock, gnss_status, gnss_status_lock):
    logger = logging.getLogger('Sbs1OgnNmeaToFlarmTransformation.InputProcessor')

    while True:
        # get executor that can run in the background (and is asyncio-enabled)
        executor = ThreadPoolExecutor(max_workers=1)

        # get new item from data hub
        data_hub_item = yield from loop.run_in_executor(executor, data_input_queue.get)

        # check if item is a poison pill
        if data_hub_item is None:
            logger.debug('Received poison pill')

            # exit loop
            break

        if type(data_hub_item) is DataHubItem:
            logger.debug('Received ' + str(data_hub_item))

            if data_hub_item.get_content_type() == 'nmea':
                yield from handle_nmea_data(data_hub_item.get_content_data(), gnss_status, gnss_status_lock)

            if data_hub_item.get_content_type() == 'sbs1':
                yield from handle_sbs1_data(data_hub_item.get_content_data(), aircraft, aircraft_lock)

            if data_hub_item.get_content_type() == 'ogn':
                yield from handle_ogn_data(data_hub_item.get_content_data(), aircraft, aircraft_lock, gnss_status)


@asyncio.coroutine
def handle_sbs1_data(data, aircraft, aircraft_lock):
    logger = logging.getLogger('Sbs1OgnNmeaToFlarmTransformation.Sbs1Handler')

    try:
        fields = data.split(',')

        msg_type = fields[1]

        # check if message is of interest
        if len(fields) > 16 and msg_type in ['1', '2', '3', '4', '5']:
            aircraft_type = fields[2]
            signallevel = fields[3]
            icao_id = fields[4] #FFFFFF no ADSB records 
            callsign = fields[10].strip()
            altitude = fields[11]
            horizontal_speed = fields[12]
            course = fields[13]
            latitude = fields[14]
            longitude = fields[15]
            vertical_speed = fields[16]           

            with aircraft_lock:
                # initialize empty AircraftInfo object if required
                if icao_id not in aircraft.keys():
                    aircraft[icao_id] = AircraftInfo()
                    aircraft[icao_id].identifier = icao_id
                    aircraft[icao_id].datatype = 'A'

                # save timestamp
                aircraft[icao_id].last_seen = time.time()
            
            if msg_type == '1':
                logger.debug("A/C identification: {} callsign={}".format(icao_id, callsign))

                with aircraft_lock:
                    aircraft[icao_id].callsign = callsign

            # handle ground and airborne position data
            elif msg_type == '2' or msg_type == '3':
                position_type = ''
                if msg_type == '2':
                    position_type = 'Ground'
                elif msg_type == '3':
                    position_type = 'Airborne'

                logger.debug('{} position: {} lat={} lon={} alt={}'.format(position_type, icao_id, latitude, longitude, altitude))

                with aircraft_lock:
                    aircraft[icao_id].latitude = float(latitude)
                    aircraft[icao_id].longitude = float(longitude)
                    aircraft[icao_id].altitude = float(altitude)

            # handle velocity data
            elif msg_type == '4':
                logger.debug('Vector: {} h_speed={} course={} v_speed={}'.format(icao_id, horizontal_speed, course, vertical_speed))

                with aircraft_lock:
                    aircraft[icao_id].h_speed = float(horizontal_speed)
                    aircraft[icao_id].v_speed = float(vertical_speed)
                    aircraft[icao_id].course = float(course)

            # handle aircraft identification data
            # A0 = No Data          B0 = no Data
            # A1 = Light            B1 = Glider
            # A2 = Medium           B2 = Ballon
            # A3 = Heavy            B3 = skydiver
            # A4 = High-Vortex      B4 = ultralight
            # A5 = Very heavy       B5 = reserved
            # A6 = High perf./speed B6 = Drone
            # A7 = Rotorcraft       B7 = Spacecraft

            elif msg_type == '5':
                logger.debug("A/C identification: {} type={} alt={}".format(icao_id, aircraft_type, altitude))

                with aircraft_lock:
                    aircraft[icao_id].signallevel = float(signallevel)
                    aircraft[icao_id].altitude = float(altitude)
                    speed = 50
                    if aircraft[icao_id].h_speed:
                        speed = aircraft[icao_id].h_speed
                    # set type to unknown
                    acft_type = '0'
                    if aircraft_type == 'A2' or aircraft_type == 'A3' or aircraft_type == 'A4' or aircraft_type == 'A5' or aircraft_type == 'A6':
                        acft_type = '9'
                    elif speed > 100:
                        acft_type = '9'                        
                    elif aircraft_type == 'A1':
                        acft_type = '8'
                    elif aircraft_type == 'A7':
                        acft_type = '3'
                    elif aircraft_type == 'B1':
                        acft_type = '1'
                    elif aircraft_type == 'B2':
                        acft_type = 'B'
                    else:
                        acft_type = '8'
                    
                    aircraft[icao_id].aircraft_type = acft_type

                    
                    
    except ValueError:
        logger.warn('Problem during SBS1 data parsing')
    except:
        logger.exception(sys.exc_info()[0])


@asyncio.coroutine
def handle_ogn_data(data, aircraft, aircraft_lock, gnss_status):
    logger = logging.getLogger('Sbs1OgnNmeaToFlarmTransformation.OgnHandler')

    logger.debug('Processing OGN data: {}'.format(data))

    # check if own location is known (required for FLARM position calculation)

    #data_parts: ['FLRDD50E2>APRS,qAR:/121255h0036.43N\\00432.58W^000/000/A=001397', '!W39!', 'id22DD50E2', '-039fpm', '+0.0rot', '40.0dB', '0e', '-1.5kHz', 'gps1x2']
    if gnss_status.longitude and gnss_status.latitude:
        try:
            data_parts = data.split(' ')

            # get first and second part
            beacon_data = data_parts[0]
			
            # get remaining parts
            position_data = data_parts[1:len(data_parts)]
			
			# beacon
            m = re.match(r"^(.+?)>APRS,(.+?):/(\d{6})+h(\d{4}\.\d{2})(N|S)(.)(\d{5}\.\d{2})(E|W)(.)((\d{3})/(\d{3}))?/A=(\d{6})", beacon_data)            
            			
            if m:
                ida = m.group(1)
                identifier = ida[-6:]
                receiver_name = m.group(2)
                timestamp = m.group(3)

                latitude = utils.conversion.ogn_coord_to_degrees(float(m.group(4)))

                if m.group(5) == "S":
                    latitude = -1.0 * latitude

                symbol_table = m.group(6)

                longitude = utils.conversion.ogn_coord_to_degrees(float(m.group(7)))
                if m.group(8) == "W":
                    longitude = -1.0 * longitude

                symbol_code = m.group(9)

                track = 0
                h_speed = 0
                if m.group(10) is not None:
                    track = int(m.group(11))
                    h_speed = int(m.group(12))

                altitude = int(m.group(13))

                if not identifier == 'FlightBox':
                    with aircraft_lock:
                        # initialize empty AircraftInfo object if required
                        if identifier not in aircraft.keys():
                            aircraft[identifier] = AircraftInfo()
                            aircraft[identifier].identifier = identifier
                            aircraft[identifier].datatype = 'F'

                        # save data
                        aircraft[identifier].last_seen = time.time()
                        aircraft[identifier].latitude = utils.calculation.lat_abs_from_rel_flarm_coordinate(gnss_status.latitude, latitude)
                        aircraft[identifier].longitude = utils.calculation.lat_abs_from_rel_flarm_coordinate(gnss_status.longitude, longitude)
                        aircraft[identifier].altitude = altitude
                        aircraft[identifier].h_speed = h_speed
                        aircraft[identifier].course = track

#                    logger.debug('{}: lat={}, lon={}, alt={}, course={:d}, h_speed={:d}'.format(identifier, aircraft[identifier].latitude, aircraft[identifier].longitude, aircraft[identifier].altitude, aircraft[identifier].course, aircraft[identifier].h_speed))

                else:
                    logger.info('Discarding receiver beacon')

            else:
                logger.warn('Problem parsing OGN beacon data: {}'.format(beacon_data))

            # compile matching patterns: FLARM data
            address_pattern = re.compile(r"id(\S{2})(\S{6})")
            climb_rate_pattern = re.compile(r"([\+\-]\d+)fpm")
            turn_rate_pattern = re.compile(r"([\+\-]\d+\.\d+)rot")
            signal_strength_pattern = re.compile(r"(\d+\.\d+)dB")
            error_count_pattern = re.compile(r"(\d+)e")
            coordinates_extension_pattern = re.compile(r"\!W(.)(.)!")
            hear_ID_pattern = re.compile(r"hear(\w{4})")
            frequency_offset_pattern = re.compile(r"([\+\-]\d+\.\d+)kHz")
            gps_status_pattern = re.compile(r"gps(\d+x\d+)")
            software_version_pattern = re.compile(r"s(\d+\.\d+)")
            hardware_version_pattern = re.compile(r"h(\d+)")
            real_id_pattern = re.compile(r"r(\w{6})")
            flightlevel_pattern = re.compile(r"FL(\d{3}\.\d{2})")

            # compile matching patterns: receiver beacon data
            ogn_decode_version_pattern = re.compile(r"v(\d\.\d\.\d\.\w+)")
            load_pattern = re.compile(r"CPU:([\d\.]+)")
            ram_pattern = re.compile(r"RAM:([\d\.]+)/([\d\.]+)(\w+)")
            ntp_pattern = re.compile(r"NTP:([\d\.-]+)ms/([\d\.-]+)ppm")
            temperature_pattern = re.compile(r"([\d\.+-]+)C")
            rf_pattern = re.compile(r"RF:([\w\d\.+-/]+)")

            for position_data_part in position_data:
                address_match = address_pattern.match(position_data_part)
                climb_rate_match = climb_rate_pattern.match(position_data_part)
                turn_rate_match = turn_rate_pattern.match(position_data_part)
                signal_strength_match = signal_strength_pattern.match(position_data_part)
                error_count_match = error_count_pattern.match(position_data_part)
                coordinates_extension_match = coordinates_extension_pattern.match(position_data_part)
                hear_ID_match = hear_ID_pattern.match(position_data_part)
                frequency_offset_match = frequency_offset_pattern.match(position_data_part)
                gps_status_match = gps_status_pattern.match(position_data_part)
                software_version_match = software_version_pattern.match(position_data_part)
                hardware_version_match = hardware_version_pattern.match(position_data_part)
                real_id_match = real_id_pattern.match(position_data_part)
                flightlevel_match = flightlevel_pattern.match(position_data_part)

                ogn_decode_version_match = ogn_decode_version_pattern.match(position_data_part)
                load_match = load_pattern.match(position_data_part)
                ram_match = ram_pattern.match(position_data_part)
                ntp_match = ntp_pattern.match(position_data_part)
                temperature_match = temperature_pattern.match(position_data_part)
                rf_match = rf_pattern.match(position_data_part)

                if address_match is not None:
                    # Flarm ID type byte in APRS msg: PTTT TTII
                    # P => stealth mode
                    # TTTTT => aircraftType
                    # II => IdType: 0=Random, 1=ICAO, 2=FLARM, 3=OGN
                    # (see https://groups.google.com/forum/#!msg/openglidernetwork/lMzl5ZsaCVs/YirmlnkaJOYJ).
                    address_type = int(address_match.group(1), 16) & 0b00000011
                    aircraft_type = (int(address_match.group(1), 16) & 0b01111100) >> 2
                    stealth = ((int(address_match.group(1), 16) & 0b10000000) >> 7 == 1)
                    address = address_match.group(2)

                    # save data
                    aircraft[identifier].aircraft_type = aircraft_type

                elif climb_rate_match is not None:
                    climb_rate = int(climb_rate_match.group(1))

                    # save data
                    aircraft[identifier].v_speed = climb_rate

                elif turn_rate_match is not None:
                    turn_rate = float(turn_rate_match.group(1))

                elif signal_strength_match is not None:
                    signal_strength = float(signal_strength_match.group(1))

                elif error_count_match is not None:
                    error_count = int(error_count_match.group(1))

                elif coordinates_extension_match is not None:
                    # position precision enhancement is third decimal digit of minute
                    lat_delta_degrees = int(coordinates_extension_match.group(1)) / 1000.0 / 60.0
                    lon_delta_degrees = int(coordinates_extension_match.group(2)) / 1000.0 / 60.0

                    latitude += lat_delta_degrees
                    longitude += lon_delta_degrees

                    # save data
                    aircraft[identifier].latitude = utils.calculation.lat_abs_from_rel_flarm_coordinate(gnss_status.latitude, latitude)
                    aircraft[identifier].longitude = utils.calculation.lat_abs_from_rel_flarm_coordinate(gnss_status.longitude, longitude)

                elif hear_ID_match is not None:
                    pass
                    # heared_aircraft_IDs.append(hear_ID_match.group(1))

                elif frequency_offset_match is not None:
                    frequency_offset = float(frequency_offset_match.group(1))

                elif gps_status_match is not None:
                    gps_status = gps_status_match.group(1)

                elif software_version_match is not None:
                    software_version = float(software_version_match.group(1))

                elif hardware_version_match is not None:
                    hardware_version = int(hardware_version_match.group(1))

                elif real_id_match is not None:
                    real_id = real_id_match.group(1)

                elif flightlevel_match is not None:
                    flightlevel = float(flightlevel_match.group(1))

                elif ogn_decode_version_match is not None:
                    ogn_decode_version = ogn_decode_version_match.group(1)

                elif load_match is not None:
                    load = float(load_match.group(1))

                elif ram_match is not None:
                    ram_used = float(ram_match.group(1))
                    ram_total = float(ram_match.group(2))
                    ram_unit = ram_match.group(3)

                elif ntp_match is not None:
                    ntp_offset_ms = float(ntp_match.group(1))
                    ntp_update_rate_ppm = float(ntp_match.group(2))

                elif temperature_match is not None:
                    temperature_celsius = float(temperature_match.group(1))

                elif rf_match is not None:
                    rf_info = rf_match.group(1)

                else:
                    logger.warn('Problem parsing OGN position data ({}): {}'.format(position_data_part, position_data))

        except ValueError:
            logger.warn('Problem during OGN data parsing')
            logger.exception(sys.exc_info()[0])
        except:
            logger.exception(sys.exc_info()[0])


@asyncio.coroutine
def handle_nmea_data(data, gnss_status, gnss_status_lock):
    logger = logging.getLogger('Sbs1OgnNmeaToFlarmTransformation.NmeaHandler')

    try:
        # check if message is of interest
        if data.startswith('$GPGGA'):
            message = pynmea2.parse(data)

            logger.debug('GPGGA: lat={} {}, lon={} {}, alt={} {}, qual={:d}, n_sat={}, h_dop={}, geoidal_sep={} {}'.format(message.lat, message.lat_dir, message.lon, message.lon_dir, message.altitude, message.altitude_units, message.gps_qual, message.num_sats, message.horizontal_dil, message.geo_sep, message.geo_sep_units))

            with gnss_status_lock:
                lat = utils.conversion.nmea_coord_to_degrees(float(message.lat))
                if message.lat_dir == 'N':
                    gnss_status.latitude = lat
                elif message.lat_dir == 'S':
                    gnss_status.latitude = -1.0 * lat

                lon = utils.conversion.nmea_coord_to_degrees(float(message.lon))
                if message.lon_dir == 'W':
                    gnss_status.longitude = -1.0 * lon
                elif message.lon_dir == 'E':
                    gnss_status.longitude = lon

                alt_m = float(message.altitude)
                if message.altitude_units == 'M':
                    gnss_status.altitude = utils.conversion.meters_to_feet(alt_m)

        elif data.startswith('$GPGLL'):
            message = pynmea2.parse(data)

#            logger.debug('GPGLL: lat={} {}, lon={} {}, status={}, pos_mode={}'.format(message.lat, message.lat_dir, message.lon, message.lon_dir, message.status, message.faa_mode))

            with gnss_status_lock:
                lat = utils.conversion.nmea_coord_to_degrees(float(message.lat))
                if message.lat_dir == 'N':
                    gnss_status.latitude = lat
                elif message.lat_dir == 'S':
                    gnss_status.latitude = -1.0 * lat

                lon = utils.conversion.nmea_coord_to_degrees(float(message.lon))
                if message.lon_dir == 'W':
                    gnss_status.longitude = -1.0 * lon
                elif message.lon_dir == 'E':
                    gnss_status.longitude = lon

        elif data.startswith('$GPVTG'):
            fields = (data.split('*')[0]).split(',')

            if len(fields) > 9:
                cog_t = fields[1]
                cog_m = fields[3]
                h_speed_kt = fields[5]
                h_speed_kph = fields[7]
                pos_mode = fields[9]

#                logger.debug('GPVTG: cog_t={}, cog_m={}, h_speed_kt={}, h_speed_kph={}, pos_mode={}'.format(cog_t, cog_m, h_speed_kt, h_speed_kph, pos_mode))

                with gnss_status_lock:
                    # check if values are available before converting
                    if h_speed_kt:
                        gnss_status.h_speed = float(h_speed_kt)
                    if cog_t:
                        gnss_status.course = float(cog_t)
    except ValueError:
        logger.info('Problem during NMEA data parsing (no fix?)')
    except:
        logger.exception(sys.exc_info()[0])


def generate_flarm_messages(gnss_status, aircraft):
    logger = logging.getLogger('Sbs1OgnNmeaToFlarmTransformation.FlarmGenerator')

    # define parameter limits (given by FLARM protocol)
    DISTANCE_M_MIN = -45000     #-32768 
    DISTANCE_M_MAX = 45000      #32767

    modec_parts = parser.get('DEFAULT','my_ICAO').split(',')
    # get icao and tail part
    my_icao = modec_parts[0]
    my_tail = modec_parts[1]
    modec_sep = float(parser.get('DEFAULT','modec_sep'))
    modec_det = float(parser.get('DEFAULT','modec_det'))

    if modec_det == 1: # ultra short
        modec_3= -29
        modec_2= -30
        modec_1= -31
    elif modec_det == 2: # short
        modec_3= -30
        modec_2= -31
        modec_1= -32        
    elif modec_det == 3: # medium
        modec_3= -31
        modec_2= -32
        modec_1= -33
    else: # long
        modec_3= -32
        modec_2= -33
        modec_1= -34   
        
    # initialize message list
    flarm_messages = []
    adsb = False
    
    if my_tail == aircraft.identifier:
        return None
    
    # check if plans are in sight
#    if aircraft.identifier == 'AAAAAA': #no plane in sight
#        """ generate PFLAA message """
#        # PFLAU,<RX>,<TX>,<GPS>,<Power>,<AlarmLevel>,<RelativeBearing>,<AlarmType>,<RelativeVertical>,<RelativeDistance>,<ID>
#        # indicate number of received devices
#        rx = '0'
#        # indicate no transmission
#        tx = '0'
#        # indicate airborne 3D fix
#        gps = '2'
#        # indicate power OK
#        power = '1'
#        # indicate no collision within next 18 seconds
#        alarm_level = '0'
#        relative_bearing = ''
#        alarm_type = '0'
#        relative_vertical = 0
#        relative_distance = ''
#        identifier = ''

#        flarm_message_laa = pynmea2.ProprietarySentence('F', ['LAU', rx, tx, gps, power, alarm_level, relative_bearing, alarm_type, relative_vertical, relative_distance, identifier])
#        #portOUT.write(str(flarm_message_laa).encode())
#        flarm_messages.append(str(flarm_message_laa))
#        logger.debug('FLARM no plane message: {}'.format(str(flarm_message_laa)))

    if gnss_status.longitude and gnss_status.latitude and aircraft.longitude and aircraft.latitude:
        """ generate PFLAA message ADS-B"""
        # PFLAA,<AlarmLevel>,<RelativeNorth>,<RelativeEast>, <RelativeVertical>,<IDType>,<ID>,<Track>,<TurnRate>,<GroundSpeed>, <ClimbRate>,<AcftType>
        adsb = True
        
        # calculate distance and bearing
        gnss_coordinates = (gnss_status.latitude, gnss_status.longitude)
        aircraft_coordinates = (aircraft.latitude, aircraft.longitude)
        distance_m = vincenty(gnss_coordinates, aircraft_coordinates).meters
        initial_bearing = utils.calculation.initial_bearing(gnss_status.latitude, gnss_status.longitude, aircraft.latitude, aircraft.longitude)
        final_bearing = utils.calculation.final_bearing(gnss_status.latitude, gnss_status.longitude, aircraft.latitude, aircraft.longitude)
        
        # calculate relative distance (north, east)
        distance_north_m = utils.calculation.distance_north(initial_bearing, distance_m)
        distance_east_m = utils.calculation.distance_east(initial_bearing, distance_m)

        # skip aircraft if distance is out of limits
        if not (distance_north_m >= DISTANCE_M_MIN and distance_north_m <= DISTANCE_M_MAX):
            return None
        if not (distance_east_m >= DISTANCE_M_MIN and distance_east_m <= DISTANCE_M_MAX):
            return None

        # set relative distance
        relative_north = '{:.0f}'.format(min(max(distance_north_m, DISTANCE_M_MIN), DISTANCE_M_MAX))
        relative_east = '{:.0f}'.format(min(max(distance_east_m, DISTANCE_M_MIN), DISTANCE_M_MAX))

#        logger.debug('{}: dist={:.0f} m, initial_bearing={:.0f} deg, final_bearing={:.0f} deg, dist_n={:.0f} m, dist_e={:.0f} m'.format(aircraft.identifier, distance_m, initial_bearing, final_bearing, distance_north_m, distance_east_m))

        relative_vertical = 0
        if gnss_status.altitude and aircraft.altitude:
            if aircraft.datatype == 'F':
                relative_vertical = '{:.0f}'.format(min(max(utils.conversion.feet_to_meters(aircraft.altitude - gnss_status.altitude), DISTANCE_M_MIN), DISTANCE_M_MAX))
            else:
                relative_vertical = '{:.0f}'.format(min(max(utils.conversion.feet_to_meters(aircraft.altitude) - utils.calculation.altimeter(), DISTANCE_M_MIN), DISTANCE_M_MAX))
                #relative_vertical = '{:.0f}'.format(min(max(utils.conversion.feet_to_meters(aircraft.altitude) - sensor.read_altitude(), DISTANCE_M_MIN), DISTANCE_M_MAX)) 
        # indicate ICAO identifier
		
        identifier_type = '1'
        identifier = aircraft.identifier
		
        if aircraft.callsign:
            identifier_type = '1'
            identifier = aircraft.identifier+"!"+aircraft.callsign
        elif aircraft.datatype == 'F':
            identifier_type = '2'
            identifier = aircraft.identifier+"!"+"Mode-F"
            
        track = ''
        if aircraft.course is not None:
            track = '{:.0f}'.format(min(max(aircraft.course, 0), 359))

        turn_rate = ''

        ground_speed = ''
        if aircraft.h_speed is not None:
            # convert knots to m/s and limit to target range
            ground_speed = '{:.0f}'.format(min(max(utils.conversion.knots_to_mps(aircraft.h_speed), 0), 32767))

        climb_rate = ''
        if aircraft.v_speed is not None:
            # convert ft/min to m/s, limit to target range, and limit to one digit after dot
            climb_rate = '{:.1f}'.format(min(max(utils.conversion.feet_to_meters(aircraft.v_speed * 0.3048) / 60.0, -32.7), 32.7))

        acft_type = str(aircraft.aircraft_type)

        alarm = False
        alarm_level = '0'
        alarm_type = '0'
        
        if 0 <= distance_m <= 1852 and -155 <= int(relative_vertical) <= 155: # 1.0NM / +-500ft
            alarm_level = '3'
            alarm_type = '2'
            alarm = True
        elif 0 <= distance_m <= 5100 and -310 <= int(relative_vertical) <= 310: # 2.0NM / +-1000ft
            alarm_level = '2'
            alarm_type = '2'
            alarm = True
        elif 0 <= distance_m <= 9700 and -620 <= int(relative_vertical) <= 620: # 5.0NM / +-2000ft
            alarm_level = '1'
            alarm_type = '2'
            alarm = True
        else:
            alarm_level = '0'
            alarm_type = '0'

        if alarm == True:
            identifier = aircraft.identifier

			
        flarm_message_laa = pynmea2.ProprietarySentence('F', ['LAA', alarm_level, relative_north, relative_east, relative_vertical, identifier_type, identifier, track, turn_rate, ground_speed, climb_rate, acft_type])
        #portOUT.write(str(flarm_message_laa).encode())
        flarm_messages.append(str(flarm_message_laa))
        logger.info('ADSB: {}'.format(str(flarm_message_laa)))

#        if gnss_status.altitude:
        if alarm == True:
            """ generate PFLAU message """
            # PFLAU,<RX>,<TX>,<GPS>,<Power>,<AlarmLevel>,<RelativeBearing>,<AlarmType>,<RelativeVertical>,<RelativeDistance>,<ID>

            # indicate number of received devices
            rx = '1'
            # indicate no transmission
            tx = '0'
            # indicate airborne 3D fix
            gps = '2'
            # indicate power OK
            power = '1'
            # set relative bearing to target
            relative_bearing = ''
            if initial_bearing and gnss_status.course:
                relative_bearing = '{:.0f}'.format(min(max(utils.calculation.relative_bearing(initial_bearing, gnss_status.course), -180), 180))
            # set relative distance to target
            relative_distance = '{:.0f}'.format(min(max(distance_m, 0), 2147483647))

            flarm_message_laa = pynmea2.ProprietarySentence('F', ['LAU', rx, tx, gps, power, alarm_level, relative_bearing, alarm_type, relative_vertical, relative_distance, identifier])
            flarm_messages.append(str(flarm_message_laa))
            logger.info('ADSB: {}'.format(str(flarm_message_laa)))
            
        else:
            rx = '1'
            # indicate no transmission
            tx = '0'
            # indicate airborne 3D fix
            gps = '2'
            # indicate power OK
            power = '1'
            # indicate no collision within next 18 seconds
            alarm_level = '0'
            relative_bearing = ''
            alarm_type = '0'
            relative_vertical = '0'
            relative_distance = ''
            identifier = ''

            flarm_message_laa = pynmea2.ProprietarySentence('F', ['LAU', rx, tx, gps, power, alarm_level, relative_bearing, alarm_type, relative_vertical, relative_distance, identifier])

            flarm_messages.append(str(flarm_message_laa))
            logger.debug('No plane message: {}'.format(str(flarm_message_laa)))


    # check if positions are known
    elif gnss_status.longitude and gnss_status.latitude and aircraft.altitude and adsb == False:
        """ generate PFLAA message for MODE A/C"""
        # PFLAA,<AlarmLevel>,<RelativeNorth>,<RelativeEast>, <RelativeVertical>,<IDType>,<ID>,<Track>,<TurnRate>,<GroundSpeed>, <ClimbRate>,<AcftType>

        #relative_vertical = '{:.0f}'.format(min(max(utils.conversion.feet_to_meters(aircraft.altitude - gnss_status.altitude), DISTANCE_M_MIN), DISTANCE_M_MAX))
        relative_vertical = '{:.0f}'.format(min(max(utils.conversion.feet_to_meters(aircraft.altitude) - utils.calculation.altimeter(), DISTANCE_M_MIN), DISTANCE_M_MAX))

        # skip aircraft if LAT is known or vertical is to high
        if aircraft.latitude or int(relative_vertical) > 1000:
            return None

        #aircraft.signallevel = 0.000332
        rssi = round(utils.conversion.db_to_rssi(aircraft.signallevel),2)
		
        identifier = aircraft.identifier+"!"+"Mode-C"
        identifier_type = '1'

        alarm = False
        alarm_level = '0'
        alarm_type = '0'
        
        if 0 >= float(rssi) >= modec_3 and -155 <= int(relative_vertical) <= 155: # +-500ft 
            alarm_level = '3'
            alarm_type = '2'
            alarm = True  
            relative_north = '1852' # 1.0NM 1852m
        elif 0 >= float(rssi) >= modec_2 and -310 <= int(relative_vertical) <= 310: # +-1000ft 
            alarm_level = '2'
            alarm_type = '2'
            alarm = True
            relative_north = '5100' # 2.0NM 5100m
        elif 0 >= float(rssi) >= modec_1 and -310 <= int(relative_vertical) <= 310: # +-1000ft
            alarm_level = '1'
            alarm_type = '2'
            alarm = True
            relative_north = '9700' # 5.0NM 9700m            
        else:
            alarm_level = '0'
            alarm_type = '0'
            return None
            #relative_north = '29100' # 15.0NM 29100m
			
        if alarm == True:
            identifier = aircraft.identifier

        relative_east = ''
        # indicate ICAO identifier
        identifier = aircraft.identifier
        #identifier = aircraft.identifier+"!"+"Mode-C"
        identifier_type = '1'
        track = ''
        turn_rate = ''
        ground_speed = ''
        climb_rate = ''
        acft_type = str(aircraft.aircraft_type)
        
        flarm_message_laa = pynmea2.ProprietarySentence('F', ['LAA', alarm_level, relative_north, relative_east, relative_vertical, identifier_type, identifier, track, turn_rate, ground_speed, climb_rate, acft_type])
        #portOUT.write(str(flarm_message_laa).encode())
        flarm_messages.append(str(flarm_message_laa))
        logger.info('Mode-C: {}'.format(str(flarm_message_laa)))

        if alarm == True: 
            """ generate PFLAU message """
            # PFLAU,<RX>,<TX>,<GPS>,<Power>,<AlarmLevel>,<RelativeBearing>,<AlarmType>,<RelativeVertical>,<RelativeDistance>,<ID>

            # indicate number of received devices
            rx = '1'
            # indicate no transmission
            tx = '0'
            # indicate airborne 3D fix
            gps = '2'
            # indicate power OK
            power = '1'
            # indicate mode ac
            relative_bearing = ''
            

            flarm_message_laa = pynmea2.ProprietarySentence('F', ['LAU', rx, tx, gps, power, alarm_level, relative_bearing, alarm_type, relative_vertical, relative_north, identifier])
            flarm_messages.append(str(flarm_message_laa))
            logger.info('Mode-C: {}'.format(str(flarm_message_laa)))    


    if len(flarm_messages) > 0:
        return flarm_messages

    return None

@asyncio.coroutine
def data_processor(loop, data_hub, aircraft, aircraft_lock, gnss_status, gnss_status_lock):
    logger = logging.getLogger('Sbs1OgnNmeaToFlarmTransformation.DataProcessor')

    while True:
        logger.debug('Processing data:')

        with gnss_status_lock:
            logger.debug('GNSS: lat={}, lon={}, alt={}, h_s={}, h={}'.format(gnss_status.latitude, gnss_status.longitude, gnss_status.altitude, gnss_status.h_speed, gnss_status.course))

        with aircraft_lock:
            for icao_id in sorted(aircraft.keys()):
                current_aircraft = aircraft[icao_id]

                age_in_seconds = time.time() - current_aircraft.last_seen

                logger.debug('{}: cs={}, lat={}, lon={}, alt={}, h_s={}, v_s={}, h={}, a={:.0f}'.format(icao_id, current_aircraft.callsign, current_aircraft.latitude, current_aircraft.longitude, current_aircraft.altitude, current_aircraft.h_speed, current_aircraft.v_speed, current_aircraft.course, age_in_seconds))

                # generate FLARM messages
                flarm_messages = generate_flarm_messages(gnss_status=gnss_status, aircraft=current_aircraft)
                if flarm_messages:
                    for flarm_message in flarm_messages:
                        data_hub_item = DataHubItem('flarm', flarm_message)
                        data_hub.put(data_hub_item)

                # delete entries of aircraft that have not been seen for a while
                if age_in_seconds > 30.0:
                    del aircraft[icao_id]

        yield from asyncio.sleep(1)


class AircraftInfo(object):
    def __init__(self):   
        self.aircraft_type = '0'
        self.signallevel = 0
        self.identifier = None
        self.callsign = None
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.h_speed = None
        self.v_speed = None
        self.course = None
        self.last_seen = None
        self.datatype = None

class GnssStatus(object):
    def __init__(self):
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.h_speed = None
        self.course = None
        self.last_update = None


class Sbs1OgnNmeaToFlarmTransformation(TransformationModule):
    def __init__(self, data_hub):
        # call parent constructor
        super().__init__(data_hub=data_hub)

        # configure logging
        self._logger = logging.getLogger('Sbs1OgnNmeaToFlarmTransformation')
        self._logger.info('Initializing')

        # initialize aircraft data structure
        self._aircraft = {}
        self._aircraft_lock = Lock()

        # initialize gnss data structure
        self._gnss_status = GnssStatus()
        self._gnss_status_lock = Lock()

    def run(self):
        setproctitle.setproctitle("flightbox_transformation_sbs1ognnmea_flarm")

        self._logger.info('Running')

        # get asyncio loop
        loop = asyncio.get_event_loop()

        # compile task list that will run in loop
        tasks = asyncio.gather(
            asyncio.async(input_processor(loop=loop, data_input_queue=self._data_input_queue, aircraft=self._aircraft, aircraft_lock=self._aircraft_lock, gnss_status=self._gnss_status, gnss_status_lock=self._gnss_status_lock)),
            asyncio.async(data_processor(loop=loop, data_hub=self._data_hub, aircraft=self._aircraft, aircraft_lock=self._aircraft_lock, gnss_status=self._gnss_status, gnss_status_lock=self._gnss_status_lock))
        )

        try:
            # start loop
            loop.run_until_complete(tasks)
        except(KeyboardInterrupt, SystemExit):
            pass
        except:
            self._logger.exception(sys.exc_info()[0])
            tasks.cancel()
        finally:
            loop.stop()

        # close data input queue
        self._data_input_queue.close()

        self._logger.info('Terminating')

    def get_desired_content_types(self):
        return(['sbs1', 'ogn', 'nmea'])
