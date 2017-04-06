#!/usr/bin/env python3

"""flightbox_watchdog.py: Script that checks if required FlightBox and OGN processes are running and (re-)starts them if required.
Can be used to start and monitor FlightBox via a cronjob."""

from os import path
from os import system
import psutil
from utils.detached_screen import DetachedScreen
import time

__author__ = "Thorsten Biermann"
__copyright__ = "Copyright 2015, Thorsten Biermann"
__email__ = "thorsten.biermann@gmail.com"


# define flightbox processes that must be running
required_flightbox_processes = {}
required_flightbox_processes['flightbox'] = {'status': None}
required_flightbox_processes['flightbox_datahubworker'] = {'status': None}
required_flightbox_processes['flightbox_output_network_airconnect'] = {'status': None}
required_flightbox_processes['flightbox_transformation_sbs1ognnmea_flarm'] = {'status': None}
required_flightbox_processes['flightbox_input_network_sbs1'] = {'status': None}
required_flightbox_processes['flightbox_input_network_ogn_server'] = {'status': None}
required_flightbox_processes['flightbox_input_serial_gnss'] = {'status': None}

# define command for starting flightbox
flightbox_command = '/home/pi/opt/flightbox/flightbox.py'

# define command for starting dump1090
dump1090_command = 'sudo systemctl start dump1090.service'

# define command for starting pcasweb
pcasweb_command = 'sudo systemctl start pcasweb.service'

# define DUMP1090 processes that must be running
required_dump1090_processes = {}
required_dump1090_processes['dump1090'] = {'status': None}

# define pcasweb processes that must be running
required_pcasweb_processes = {}
required_pcasweb_processes['pcasweb'] = {'status': None}

#Flightbox
def check_flightbox_processes():
    global required_flightbox_processes

    for p in psutil.process_iter():
        if p.name() in required_flightbox_processes.keys():
            required_flightbox_processes[p.name()]['status'] = p.status()

def kill_all_flightbox_processes():
    for p in psutil.process_iter():
        if p.name().startswith('flightbox'):
            print("Killing process {}".format(p.name()))
            p.kill()

def start_flightbox():
    global flightbox_command

    print("Starting flightbox inside screen")
    s = DetachedScreen('flightbox', command=flightbox_command, initialize=True)
    s.disable_logs()
    time.sleep(5.0)

def restart_flightbox():
    kill_all_flightbox_processes()
    time.sleep(15.0)
    start_flightbox()

#PCAS WEB
def check_pcasweb_processes():
    global required_pcasweb_processes

    for p in psutil.process_iter():
        if p.name() in required_pcasweb_processes.keys():
            required_pcasweb_processes[p.name()]['status'] = p.status()

def kill_all_pcasweb_processes():
    for p in psutil.process_iter():
        if p.name().startswith('pcasweb.sh'):            
            print("Killing process {}".format(p.name()))
            system('sudo killall pcasweb')
            system('sudo systemctl stop pcasweb.service')
            #p.kill()

def start_pcasweb():
    global pcasweb_command

    print("Starting pcasweb inside screen")
    system('sudo systemctl start pcasweb.service')
    #system('sudo bash /etc/init.d/pcasweb.sh start')
    #s = DetachedScreen('pcasweb', command=pcasweb_command, initialize=True)
    #s.disable_logs()
    time.sleep(5.0)

def restart_pcasweb():
    kill_all_pcasweb_processes()
    time.sleep(15.0)
    start_pcasweb()


#DUMP1090
def check_dump1090_processes():
    global required_dump1090_processes

    for p in psutil.process_iter():
        if p.name() in required_dump1090_processes.keys():
            required_dump1090_processes[p.name()]['status'] = p.status()

def kill_all_dump1090_processes():
    for p in psutil.process_iter():
        #print (p)
        if p.name().startswith('dump1090'):            
            print("Killing process {}".format(p.name()))
            system('sudo killall dump1090')
            system('sudo systemctl stop dump1090.service')
            p.kill()

def start_dump1090():
    global dump1090_command

    print("Starting dump1090 inside screen")
    system('sudo systemctl start dump1090.service')
    #s = DetachedScreen('dump1090', command=dump1090_command, initialize=True)
    #s.disable_logs()
    time.sleep(5.0)

def restart_dump1090():
    kill_all_dump1090_processes()
    time.sleep(15.0)
    start_dump1090()


# check if script is executed directly
if __name__ == "__main__":
    check_flightbox_processes()
    check_dump1090_processes()
    check_pcasweb_processes()

    is_flightbox_restart_required = False
    is_dump1090_restart_required = False
    is_pcasweb_restart_required = False

    for p in required_flightbox_processes.keys():
        if required_flightbox_processes[p]['status'] not in ['running', 'sleeping']:
            print("{} not running".format(p))
            is_flightbox_restart_required = True

    for p in required_dump1090_processes.keys():
        if required_dump1090_processes[p]['status'] not in ['running', 'sleeping']:
            print("{} not running".format(p))
            is_dump1090_restart_required = True

    for p in required_pcasweb_processes.keys():
        if required_pcasweb_processes[p]['status'] not in ['running', 'sleeping']:
            print("{} not running".format(p))
            is_pcasweb_restart_required = True

    if is_flightbox_restart_required:
        time.sleep(2.0)
        print('== Restarting FlightBox')
        restart_flightbox()

    if is_dump1090_restart_required:
        time.sleep(2.0)
        print('== Restarting DUMP1090')
        restart_dump1090()

    if is_pcasweb_restart_required:
        time.sleep(2.0)
        print('== Restarting PCASweb')
        restart_pcasweb()
        

