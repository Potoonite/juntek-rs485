import serial
import paho.mqtt.publish as publish
import systemd_watchdog
import datetime

## Communication Protocol http://68.168.132.244/KG-F_EN_manual.pdf Page 22
"""
Actual Example
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
"""

wd = systemd_watchdog.watchdog()
if wd.is_enabled:
    # Report a status message
    wd.status("Starting serial port ...")

try:
    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=3)
except:
    if wd.is_enabled:
        wd.status("Serial port failed to open.")
        wd.notify_error("Serial port failed to open.")
    else:
        print("Serial port failed to open.")
        raise IOError
    exit()


ignoreCmd = b':R50=01.\r\n'
responsePrefix = b':r50=1,' # b':r50=1,34,5166,1030,109337,11738441,62100651,48663,125,0,99,0,644,9117,\r\n'
tag = "SolarBattery"
totalAh = 1250.00
mode = "" 
#mode = "screen"

# Attempts to be similar to mpp-solar format in case I could integrate back https://github.com/jblance/mpp-solar 
# Starts from after responsePrefix
# fmt[4] is for [min, max] range check.
# fmt[5] is for max value delta per second check.
responseFmt = {
    'KG' : [
        ["discard", 1, "checksum", ""],
        ["String2Int:r/100", 1, "Battery Bank Voltage", "V", [40, 60], 5],
        ["String2Float:r/100", 1, "Current", "A", [-400, 400]],
        ["String2Float:r/1000", 1, "Remaining Battery Capacity", "Ah", [0, totalAh + 50], 50],
        ["String2Float:r/1000", 2, "Cumulative Capacity", "Ah"],
        ["String2Float:r/100000", 2, "Watt-Hour", "kw.h"],
        ["String2Int", 2, "Runtime", "Sec"],
        ["String2Int:r%100", 2, "Temperature", "°C", [-30, 100]],
        ["String2Float:r/100", 1, "Power", "W", [-30000, 30000]],
        [
            #"keyed",  # Actual returned value 99. No definition
            "discard",
            "Output Status",
            {
                b"0": "On",
                b"1": "Over Voltage Protection",
                b"2": "Over Current Protection",
                b"3": "Low Voltage Protection",
                b"4": "Negative Current Protection",
                b"5": "Over Power Protection",
                b"6": "Over Temperature Protection",
                b"255": "Off",
            },
        ],
        [
            "keyed",
            "Current Direction",
            {
                b"0": "Discharging",
                b"1": "Charging",
            },
        ],
        ["String2Int", 2, "Battery Life", "Minute"],
        ["String2Float:r/100", 2, "Internal Resistance", "mΩ"],
        ["discard", 1, "CRLF", ""]
    ],
    'KH' : [
        ["discard", 1, "checksum", ""],
        ["String2Int:r/100", 1, "Battery Bank Voltage", "V", [40, 60], 5],
        ["String2Float:r/100", 1, "Current", "A", [-400, 400]],
        ["String2Float:r/1000", 1, "Remaining Battery Capacity", "Ah", [0, totalAh + 50], 50],
        ["String2Float:r/1000", 2, "Cumulative Capacity", "Ah"],
        ["String2Float:r/100000", 2, "Watt-Hour (Charging)", "kw.h"],
        ["String2Float:r/100000", 2, "Watt-Hour (DisCharging)", "kw.h"],
        ["String2Int", 2, "OpRecordValue", "Recs"],
        ["String2Int:r%100", 2, "Temperature", "°C", [-30, 100]],
        ["String2Float:r/100", 1, "Power", "W", [-30000, 30000]],
        [
            "keyed",
            "Current Direction",
            {
                b"0": "Discharging",
                b"1": "Charging",
            },
        ],
        ["String2Int", 2, "Battery Life", "Minute"],
        ["String2Int", 2, "Time Adjustment", "Minute"],
        ["String2Int", 2, "Date", "Day..."],
        ["String2Int", 2, "Time", "Sec..."],
        ["discard", 1, "CRLF", ""]
    ],
}

def String2Int(raw, adj):
    r = int(raw)
    if adj is not None:
        r = eval(adj)
    return r

def String2Float(raw, adj):
    r = float(raw)
    if adj is not None:
        r = eval(adj)
    return r

def keyed(raw, options):
    r = options[raw]
    return r

def parse1Field(field, fmt):
    dataType = fmt[0]
    if ":" in dataType:
        dataType, adj = dataType.split(":")
    else:
        adj = None
    if dataType == "discard":
        return (None, field, None)
    elif dataType == "keyed":
        return (fmt[1], keyed(field, fmt[2]), "")
    else:
        val = eval(dataType)(field, adj)
        if len(fmt) >= 5 and len(fmt[4]) == 2:
            # range check
            if val < fmt[4][0] or val > fmt[4][1]:
                raise ValueError("Field value out of range")
        return (fmt[2], eval(dataType)(field, adj), fmt[3])


def parseResponse(fields, respFmt) -> dict:
    result = []
    adjustDep = {
                    "Current" : [0.0, False],
                    "Current Direction" : ["", False],
                    "Remaining Battery Capacity" : [0.0, False],
                }

    if len(fields) != len(respFmt):
        print(f"Field count {len(fields)} != expected format count {len(respFmt)}")
        print(f"Fields {fields}")
        raise TypeError("Response count != expected format count")

    for (field, fmt) in zip(fields, respFmt):
        try:
            (name, value, unit) = parse1Field(field,fmt)
        except ValueError as e:
            raise e

        if name is not None:
            result.append([name, value, unit])
            #print(f"{name}\t\t\t\t{value}{unit}")
            if name in adjustDep:
                adjustDep[name] = [value, True]
    # Adjust Current field
    if adjustDep["Current"][1] and adjustDep["Current Direction"][1] and adjustDep["Current Direction"][0] == "Discharging":
        for r in filter(lambda row: row[0] == "Current", result):
            r[1] = -r[1]

    # Add Capacity %
    if adjustDep["Remaining Battery Capacity"][1]:
        result.append(["Battery SOC", round(adjustDep["Remaining Battery Capacity"][0] / totalAh * 100, 2), "%"])

    return result

def sendMQTT(data, TestMode=False):
    msgs = []
    for (_key, value, unit) in data:
        if _key == "Current Direction":
            continue
        # remove spaces
        key = _key.replace(" ", "_")
        #if not keep_case:
            # make lowercase
        #    key = key.lower()
        #if key_wanted(key, filter, excl_filter):
        if True:
            #
            # CONFIG / AUTODISCOVER
            #
            # <discovery_prefix>/<component>/[<node_id>/]<object_id>/config
            # topic "homeassistant/binary_sensor/garden/config"
            # msg '{"name": "garden", "device_class": "motion", "state_topic": "homeassistant/binary_sensor/garden/state", "unit_of_measurement": "°C"}'
            if not TestMode:
                topic = f"homeassistant/sensor/mpp_{tag}_{key}/config"
            else:
                topic = f"ha/sensor/mpp_{tag}_{key}/config"
            topic = topic.replace(" ", "_")
            name = f"{tag} {_key}"
            if unit == "W":
                if not TestMode:
                    payload = f'{{"name": "{name}", "state_topic": "homeassistant/sensor/mpp_{tag}_{key}/state", "unit_of_measurement": "{unit}", "unique_id": "mpp_{tag}_{key}", "state_class": "measurement", "device_class": "power"  }}'
                else:
                    payload = f'{{"name": "{name}", "state_topic": "ha/sensor/mpp_{tag}_{key}/state", "unit_of_measurement": "{unit}", "unique_id": "mpp_{tag}_{key}", "state_class": "measurement", "device_class": "power"  }}'
            else:
                if not TestMode:
                    payload = f'{{"name": "{name}", "state_topic": "homeassistant/sensor/mpp_{tag}_{key}/state", "unit_of_measurement": "{unit}", "unique_id": "mpp_{tag}_{key}"  }}'
                else:
                    payload = f'{{"name": "{name}", "state_topic": "ha/sensor/mpp_{tag}_{key}/state", "unit_of_measurement": "{unit}", "unique_id": "mpp_{tag}_{key}"  }}'
            # msg = {"topic": topic, "payload": payload, "retain": True}
            msg = {"topic": topic, "payload": payload}
            msgs.append(msg)
            #
            # VALUE SETTING
            #
            # unit = data[key][1]
            # 'tag'/status/total_output_active_power/value 1250
            # 'tag'/status/total_output_active_power/unit W
            if not TestMode:
                topic = f"homeassistant/sensor/mpp_{tag}_{key}/state"
            else:
                topic = f"ha/sensor/mpp_{tag}_{key}/state"
            msg = {"topic": topic, "payload": value}
            msgs.append(msg)
    if len(msgs) > 0:
        publish.multiple(msgs, hostname="localhost") #, port=mqtt_port, auth=auth)

if ser.is_open and wd.is_enabled:
    wd.status("Serial port Ready, start polling")
    wd.ready()
lastResult = []
lastTimestamp = datetime.datetime.now()
while ser.is_open:
    if wd.is_enabled:
        #wd.status("Waiting for serial input...")
        wd.notify()
    try:
        line = ser.readline()
        if line[:len(ignoreCmd)] == ignoreCmd:
            continue
        if line[:len(responsePrefix)] == responsePrefix:
            # Identify version by length
            fields = line[len(responsePrefix):].split(b',')
            respFmt = list(filter(lambda a: len(a) == len(fields), responseFmt.values()))[0]
            if len(respFmt) == 0:
                if wd.is_enabled:
                    wd.status(f"No matching format parsing response {line[len(responsePrefix):]}")
                else:
                    print(f"No matching format parsing response {line[len(responsePrefix):]}")
                continue

            # Parse output
            try:
                result = parseResponse(fields, respFmt)
            except ValueError as e:
                continue
            except Exception as e:
                if wd.is_enabled:
                    wd.status(f"Exception {e} parsing response {line[len(responsePrefix):]}")
                else:
                    print(f"Exception {e} parsing response {line[len(responsePrefix):]}")
                continue
            
            # check with last result to detect abnormal value changes
            if len(lastResult) == len(result):
                elapsed = datetime.datetime.now() - lastTimestamp
                elapsed = max(1.0, elapsed.total_seconds())
                for (lastRes, res, fmt) in zip(lastResult, result, respFmt):
                    if len(fmt) < 6 or lastRes[0] != res[0]:
                        continue
                    #print(f"Comparing {lastRes[1]} - {res[1]} with {fmt[5]} * {elapsed}")
                    if abs(lastRes[1] - res[1]) > fmt[5] * elapsed:
                        raise ValueError("Value change rate out-of-bound")

            if len(result) > 0:
                lastResult = result
                lastTimestamp = datetime.datetime.now()
                if mode == "screen":
                    for (name, value, unit) in result:
                        print("{:<30} {}{}".format(name, value, unit))
                else:
                    sendMQTT(result, TestMode=False)

    except KeyboardInterrupt:
        if wd.is_enabled:
            wd.status("Keyboard Interrupt")
        break
    except ValueError:
        continue
    
ser.close()
