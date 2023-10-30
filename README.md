[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](
https://github.com/custom-components/hacs)

# WundaSmart Integration for Home Assistant

A Home Assistant integration to monitor and control WundaSmart heating systems.

Individual rooms can be monitored and controled as [Climate](https://developers.home-assistant.io/docs/core/entity/climate/) entities in Home Assistant, for example, using the basic [Thermostat card](https://www.home-assistant.io/dashboards/thermostat/).

If you have a water heater connected to your WundaSmart Hub Switch that can be controlled as a [Water Heater](https://developers.home-assistant.io/docs/core/entity/water-heater) Home Assistant entity.

This integration is still in development and may not work for your specific requirements.

## Installation

Installing via HACS is recommended.

### Install using HACS:

1. Go to HACS, select `Integrations`, click the three dots menu and select 
`Custom Repositories`.

2. Add the path to this Github repository in the first field, select `Integration` as category and click `Add`.

3. Restart Home Assistant.

4. Got to the `Integrations` screen under `Settings` / `Devices and Services`.

5. Click the `Add Integration` button and select the `WundaSmart` integration.

6. Enter the IP address or host name of your WundaSmart Hub Switch, username and password.

When set up correctly all rooms configured in your Hub Switch will appear as climate entities automatically.

### Finding your user name and password

The easiest way of finding your local username and password for the Hub Switch is to use a network traffic capture app on your device that you used to set up and configure the Hub Switch.

One example you can use is the iPhone app `HTTP Traffic Capture`. This installs a VPN on your phone, allowing you to capture traffic between your phone and the Hub Switch. Start capturing, then do something in the WundaSmart app, then look at the captured traffic and your username and password will be visible in one of the requests.

## Tested Hardware

This integration is still in development but has been used with the following WundaSmart devices:

- WundaSmart Hub Switch
- WundaSmart Underfloop Heating Connection Box
- WundaSmart Radiator Head
- WundaSmart Room Thermostat
- WundaSmart Screenless Room Thermostat

## Credits

This project is a fork of https://github.com/ob0t/hawundasmart.
