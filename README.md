Read from common shunts found on Amazon through RS485. Export to screen or Home Assistant format through MQTT

## Install
Create venv and install the requirements

```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

Run using the venv python

`/home/{yourUserName}/juntek-rs485/venv/bin/python /home/{yourUserName}/juntek-rs485/juntekrs485.py`

## Configuration Variables in `juntekrs485.py`
Customize to your setup:

1. `totalAh = 1300.00`
	- The total battery capacity in ampere-hours (Ah). Used for calculations like battery state of charge (SOC).

2. `tag = "SolarBattery"`
	- A string label/tag for the battery system. Used in MQTT topic and sensor naming.

3. `mode = ""`
	- Operation mode. If set to `"screen"`, output is printed to the console; otherwise, data is sent via MQTT. Mainly use as troubleshooting and testing before deployment to MQTT

