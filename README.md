# juntek-rs485
# Juntek DC KG140F Coulometer RS-485 to Home Assistant MQTT

Juntek DC KG140F is a Coulometer. It uses a shunt to measure DC current. There are several brands on Amazon and Aliexpress.

According to the Manual:
>JUNCTEK is a registered trademark of Hangzhou Junce Instruments Co., Ltd.

## Hardware requirements
* KG-F Series Coulometer or other hardware that confirms to the same output format as described in the Juntek (or Junctek) [manual](http://68.168.132.244/KG-F_EN_manual.pdf).
* RS-485 to USB or Serial Adaptor.
* An attached screen to KG-F. This is technically optional. The screen automatically sends a command to the Coulometer to trigger a statistics response. The script simply reads the results. The script could also be modified to send the command itself if needed.

## Software requirements
* Python 3
* MQTT Broker
* Home Assistant MQTT Integration (Or any other MQTT consumers)

## Overview and Usage
[This script](juntekrs485.py) reads from a serial port and decode the plaintext output from the Juntek device.
Edit the following variables in the [python script](juntekrs485.py):
* ser: Point to your actual serial port
* tag: Name the Entity prefix you would like the MQTT topic to use.
* totalAh: Assuming you are using the Coulometer to monitor a battery or battery bank, provide the total Ah capacity of the battery for calculating State of Charge (SoC).

Search for the line `publish.multiple` and customize for your MQTT broker.

For testing purposes, change the `mode` variable to `"screen"` and it'll print the output to stdout instead of MQTT.

### Juntek Message Format
Formats are described in the manual. Here is an example:
```
b':r50=1,34,5166,1030,109337,11738441,62100651,48663,125,0,99,0,644,9117,\r\n'
Description Example 
b':r50=2,215,2056,200, 5408,4592,9437,14353,134,4112,0,0,162,30682,\r\n'

2 represents the communicationaddress;
215 represents the checksum;
2056 represents the voltage of 20.56V;
200 represents current 2.00A;
5408 represents the remaining battery capacity is 5.408Ah;
4593 means the cumulative capacity is 4.593Ah;
9437 represents the watt-hour is 0.09437kw.h;
14353 represents the running time of 14353s;
134 represents the ambient temperature is 34℃;
4112 represents the power of 41.12W;
0 means the output status is ON;
(0-ON, 1-OVP, 2-OCP, 3-LVP, 4-NCP,5-OPP, 6-OTP, 255-OFF)
0 represents the direction of current, and the current is forward current;
(0-forward, 1-reverse)
162 means battery life is 162minutes;
30682 represents the internal resistance of the battery is 306.82mΩ. 
```