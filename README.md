# FlightBox

FlightBox is a modular, event-based processing framework for aviation-related data, writen in Python. It can be used, e.g., to receive GNSS/GPS, ADS-B and FLARM signals, process them, and provide a data stream to navigation systems, like SkyDemon.  These systems then can show surrounding aircraft positions in their moving map displays.

For receiving ADS-B and FLARM signals, two DVB-T USB dongles with a certain chip set, which are compatible to the rtl-sdr tools (<http://sdr.osmocom.org/trac/wiki/rtl-sdr>), are required.

Currently, the default configuration assumes that the FlightBox files are located at `/home/pi/opt/flightbox`, and OGN receiver tools in `/home/pi/opt/rtlsdr-ogn`.  There is a watchdog script called `flightbox_watchdog.py`, which starts and monitors all required processes except the `dump1090` daemon (required for receiving ADS-B data).  This watchdog can, e.g., be executed by a cronjob to automatically start the framework after boot and make sure it keeps running.

## Requirements

Below are requirements from the hardware and software perspective.  Note that a system with reduced features, like only receiving ADS-B, works, too.

### Hardware

* Computing device, like Raspberry Pi 3
* DVB-T USB dongle that is supported by rtl-sdr (one required for ADS-B reception and another one for receiving FLARM)
* GNSS (GPS/GLONASS) USB dongle
  * E.g., with u-blox 8 chipset

### Software

* ADS-B decoder that provides SBS1 data stream, like dump1090
* OGN FLARM decoder

## Modules

FlightBox is implemented in a modular way to allow adding additional data sources (input modules), data processing steps (transformation modules), and output interfaces (output modules) in a simply way.  The modules that are currently implemented are described in the following subsections.

The data flows through a central data structure called `data_hub`.  Input and transformation modules can inject data into the system by creating a `data_hub_item` and handing it over to the data hub.  Output and transformation modules can subscribe to certain `data_hub_item` types, like `nmea` or `sbs1`.  A `data_hub_worker` processes all incoming data hub items and forwards them to the registered output and transformation modules as desired.


### Output

#### AIR Connect server

AIR Connect (<http://www.air-avionics.com/air/index.php/en/products/apps-and-interface-systems/air-connect-interface-for-apps>) is a popular interface for providing serial data, like FLARM NMEA messages, via a network connection to a variety of navigation systems and apps.  The `output_network_airconnect` module implements a server that allows apps to connect and receive position and traffic information from the FlightBox system.  The module consumes NMEA and FLARM messages (types `nmea` and `flarm`) from the data hub and forwards them to the connected clients.

