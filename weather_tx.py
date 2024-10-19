import threading, zmq, math, time, requests
from gps import *
from datetime import datetime
from enum import Enum


# Function to get weather data
def get_weather(latitude, longitude):
    try:
        weather_url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={latitude}&lon={longitude}"
        weather_response = requests.get(weather_url, headers={"User-Agent": "YourAppName"}, verify=False)  # Disable SSL verification
        weather_response.raise_for_status()

        weather_data = weather_response.json()
        temperature = weather_data['properties']['timeseries'][0]['data']['instant']['details']['air_temperature']
        wind_speed = weather_data['properties']['timeseries'][0]['data']['instant']['details']['wind_speed']
        weather_condition_code = weather_data['properties']['timeseries'][0]['data']['next_1_hours']['summary']['symbol_code']
        
        # Directly return the weather condition code from the API
        return temperature, wind_speed, weather_condition_code
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving weather data: {e}")
        return None, None, None

# GPS Setup
gpsd = gps(mode=WATCH_ENABLE|WATCH_NEWSTYLE)

# GPS Data Fetch
def getPositionData(gps):
    nx = gps.next()
    if nx is not None and nx['class'] == 'TPV':
        latitude = getattr(nx, 'lat', "Unknown")
        longitude = getattr(nx, 'lon', "Unknown")
        altitude = getattr(nx, 'alt', "Unknown")
        speed = getattr(nx, 'speed', "Unknown")
        return [latitude, longitude, altitude, speed]
    return None

# Cartesian Conversion
def get_cartesian(lat=None, lon=None):
    lat, lon = math.radians(lat), math.radians(lon)
    R = 6371  # Earth's radius
    x = R * math.cos(lat) * math.cos(lon)
    y = R * math.cos(lat) * math.sin(lon)
    z = R * math.sin(lat)
    return x, y, z

# Heading Calculation
def get_heading(aLocation):
    off_x = aLocation[-1][1] - aLocation[-2][1]
    off_y = aLocation[-1][0] - aLocation[-2][0]
    heading = 90.00 + math.atan2(-off_y, off_x) * 57.2957795
    if heading < 0:
        heading += 360.00
    return heading

# Timestamp and Time Formatting
def get_current_time():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    return now

# Encoding/Decoding Functions
def decoded(s):
    return int.from_bytes(s, 'little')

def encoded(value, length):
    return value.to_bytes(length, 'little')

def sdecoded(s):
    return int.from_bytes(s, 'little', signed=True)

def sencoded(value, length):
    return value.to_bytes(length, 'little', signed=True)

# Integer8, Integer16, Integer32, and Integer48 Classes
class Integer8():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 1)

    def decode(self, s):
        self.value = decoded(s[:1])
        return s[1:]

class Integer16():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 2)

    def decode(self, s):
        self.value = decoded(s[:2])
        return s[2:]

class Integer32():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 4)

    def decode(self, s):
        self.value = decoded(s[:4])
        return s[4:]

class Integer48():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 6)

    def decode(self, s):
        self.value = s[:6].hex()
        return s[6:]

# SInteger8 and Opaque Classes
class SInteger8():
    def __init__(self):
        self.value = None

    def encode(self):
        return sencoded(self.value, 1)

    def decode(self, s):
        self.value = sdecoded(s[:1])
        return s[1:]

class Opaque():
    def __init__(self):
        self.value = None

    def encode(self):
        return self.value.encode('utf-8')

# Enum for Modes
class Mode(Enum):
    SPS_MODE = 1
    ADHOC_MODE = 2

# hle_wsmp Class
class hle_wsmp():
    def __init__(self):
        self.mode = Integer8()
        self.ch_id = Integer8()
        self.time_slot = Integer8()
        self.data_rate = Integer8()
        self.tx_pow = SInteger8()
        self.ch_ld = Integer8()
        self.info = Integer8()
        self.usr_prio = Integer8()
        self.expiry_time = Integer8()
        self.mac = Integer48()
        self.psid = Integer32()
        self.dlen = Integer16()
        self.data = None

    def encode(self):
        return (self.mode.encode() + self.ch_id.encode() + self.time_slot.encode() +
                self.data_rate.encode() + self.tx_pow.encode() + self.ch_ld.encode() +
                self.info.encode() + self.usr_prio.encode() + self.expiry_time.encode() +
                self.mac.encode() + self.psid.encode() + self.dlen.encode() + self.data)

# Fill WSMP Content
def FillWsmpContent(data):
    hle_msg = hle_wsmp()
    hle_msg.mode.value = Mode.SPS_MODE.value
    hle_msg.ch_id.value = 172
    hle_msg.time_slot.value = 0
    hle_msg.data_rate.value = 12
    hle_msg.tx_pow.value = -9
    hle_msg.ch_ld.value = 0
    hle_msg.info.value = 0
    hle_msg.expiry_time.value = 0
    hle_msg.usr_prio.value = 0
    hle_msg.mac.value = 16557351571215
    hle_msg.psid.value = 32
    hle_msg.dlen.value = len(data)
    hle_msg.data = bytes(data, 'utf-8')
    return hle_msg.encode()

# WSMP Operation
def wsmp_operation():
    wsmp_context = zmq.Context()
    wsmp_socket = wsmp_context.socket(zmq.REQ)
    wsmp_socket.connect("tcp://localhost:5555")

    k = []
    alocation = [[0, 0]]
    cnt = 0

    while True:
        gps_data = getPositionData(gpsd)
        if gps_data is not None:
            cnt += 1
            latitude, longitude, altitude, speed = gps_data
            alocation.append([latitude, longitude])
            heading_angle = get_heading(alocation)

            temperature, wind_speed, weather_condition = get_weather(latitude, longitude)

            current_time = get_current_time()
            application_data = (f"speed={speed}\n,latitude={latitude},longitude={longitude},"
                                f"altitude={altitude}\n,heading_angl={heading_angle},"
                                f"temperature={temperature},wind_speed={wind_speed},"
                                f"condition={weather_condition}\n,transmitted_timestamp={current_time},cnt={cnt}")
            
            print(f"Transmitting: {application_data}")

            result = FillWsmpContent(application_data)
            wsmp_socket.send(result)
            msg = wsmp_socket.recv()
            print(f"Received: {msg}")
            time.sleep(0.1)

# WME Operation
class Action(Enum):
    Add = 1
    Delete = 2

class wme_sub():
    def __init__(self):
        self.action = Integer8()
        self.psid = Integer32()
        self.appname = Opaque()

    def encode(self):
        return self.action.encode() + self.psid.encode() + self.appname.encode()

def Wme_operation():
    wme_context = zmq.Context()
    wme_socket = wme_context.socket(zmq.REQ)
    wme_socket.connect("tcp://localhost:9999")

    psid_sub_mag = wme_sub()
    psid_sub_mag.action.value = Action.Add.value
    psid_sub_mag.psid.value = 32
    psid_sub_mag.appname.value = "TX_APPLICATION"
    out = psid_sub_mag.encode()
    wme_socket.send(out)
    cmh_recv_msg = wme_socket.recv()
    print("psid 32 subscribed to WME")

# Main Execution
if __name__ == "__main__":
    Wme_operation()
    app_operation_thread = threading.Thread(target=wsmp_operation)
    app_operation_thread.start()

