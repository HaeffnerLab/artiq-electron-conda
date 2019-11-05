import serial
import time
from serial.tools import list_ports


def ascii_to_hex(char):
    return hex(ord(char))


def hex_to_decimal(h):
    return int(h, 16)


def compute_checksum(l):
    tval = 0
    for c in l:
        tval += hex_to_decimal(ascii_to_hex(c))
    return hex(tval)[-2:]


def hexc2dec(bufp):
    newval = 0
    divvy = 4096
    for pn in range(1, 5):
        vally = ord(bufp[pn])
        if vally < 97:
            subby = 48
        else:
            subby = 87
        newval += (ord(bufp[pn]) - subby) * divvy
        divvy /= 16
        if newval > 32767:
            newval = newval - 65536
    return newval


def dec2hex(dec):
    h = hex(dec).split("x")[-1]
    return "0" * (4 - len(h)) + h


def find_address(identifier=None):
    """
    Find the address of a serial device. It can either find the address using
    an identifier given by the user or by manually unplugging and plugging in
    the device.
    Input:
    `identifier`(str): Any attribute of the connection. Usually USB to Serial
        converters use an FTDI chip. These chips store a number of attributes
        like: name, serial number or manufacturer. This can be used to
        identify a serial connection as long as it is unique. See the pyserial
        list_ports.grep() function for more details.
    Returns:
    The function prints the address and serial number of the FTDI chip.
    `port`(obj): Returns a pyserial port object. port.device stores the
        address.

    """
    found = False
    if identifier is None:
        port = [i for i in list(list_ports.grep(identifier))]

        if len(port) == 1:
            print('Device address: {}'.format(port[0].device))
            found = True
        elif len(port) == 0:
            print('''No devices found using identifier: {}
            \nContinue with manually finding USB address...\n'''.format(identifier))
        else:
            for p in connections:
                print('{:15}| {:15} |{:15} |{:15} |{:15}'.format('Device', 'Name', 'Serial number', 'Manufacturer', 'Description') )
                print('{:15}| {:15} |{:15} |{:15} |{:15}\n'.format(str(p.device), str(p.name), str(p.serial_number), str(p.manufacturer), str(p.description)))
            raise Exception("""The input returned multiple devices, see above.""")

    if not found:
        print('Performing manual USB address search.')
        while True:
            input('    Unplug the USB. Press Enter if unplugged...')
            before = list_ports.comports()
            input('    Plug in the USB. Press Enter if USB has been plugged in...')
            after = list_ports.comports()
            port = [i for i in after if i not in before]
            if port != []:
                break
            print('    No port found. Try again.\n')
        print('Device address: {}'.format(port[0].device))
        try:
            print('Device serial_number: {}'.format(port[0].serial_number))
        except Exception:
            print('Could not find serial number of device.')


class device:

    def __init__(self, address):
        self.address = address
        self.open()
        self.close()

    def open(self):
        self.ser = serial.Serial(self.address, 115200, timeout=1)

    def close(self):
        self.ser.close()

    def convert(self, s):
        bst = [b"*"]
        CCDDDDSS = s + compute_checksum(s)
        for char in CCDDDDSS:
            bst.append(char.encode("utf-8"))
        bst.append(b"\r")
        return bst

    def get_val(self, s):
        self.open()
        bst = self.convert(s)
        buff = [0] * 13
        for b in bst:
            self.ser.write((b))
            time.sleep(0.001)
        for b in range(0, 8):
            buff[b] = self.ser.read(1)
            time.sleep(0.001)
        self.close()
        return buff

    def set_val(self, s, val):
        self.open()
        bst = self.convert(s + val)
        for b in bst:
            self.ser.write((b))
            time.sleep(0.001)
        self.close()

    def get_temp(self):
        return hexc2dec(self.get_val("010000")) / 10.0

    def get_power_output(self):
        return hexc2dec(self.get_val("020000")) / 511.0

    def get_alarm_status(self):
        bst = self.get_val("030000")[1:5]
        s = ""
        for b in bst:
            s += str(b.decode("utf-8"))
        code = list(bin(int(s, 16))[2:])
        mssg = "".join(code) + "\n"
        code = list(reversed(code))
        if code[0] == "1":
            mssg += "HIGH ALARM 1\n"
        if code[1] == "1":
            mssg += "LOW ALARM 1\n"
        if code[2] == "1":
            mssg += "HIGH ALARM 2\n"
        if code[3] == "1":
            mssg += "LOW ALARM 2\n"
        if code[4] == "1":
            mssg += "OPEN CONTROL SENSOR\n"
        if code[5] == "1":
            mssg += "OPEN SECONDARY SENSOR\n"
        try:
            if code[6] == "1":
                mssg += "a value has changed via keypad entry\n"
        except:
            pass
        return mssg

    def get_set_temp(self):
        return hexc2dec(self.get_val("500000")) / 10.0

    def set_set_temp(self, temp):
        temp *= 10.0
        if temp < 0:
            temp += 2**16
        h = dec2hex(int(temp))
        self.set_val("1c", h)

    def get_Pgain(self):
        return hexc2dec(self.get_val("510000")) / 10.0

    def set_Pgain(self, g):
        g *= 10.0
        h = dec2hex(int(g))
        self.set_val("1d", h)

    def get_Igain(self):
        return hexc2dec(self.get_val("520000")) / 100.0

    def set_Igain(self, g):
        g *= 100.0
        h = dec2hex(int(g))
        self.set_val("1e", h)

    def get_Dgain(self):
        return hexc2dec(self.get_val("530000")) / 10.0

    def set_Dgain(self, g):
        g *= 10.0
        h = dec2hex(int(g))
        self.set_val("1f", h)

    def get_alarm1(self):
        rval = self.get_val("5b0000")
        if rval[4] == b"1":
            return "ON"
        else:
            return "OFF"

    def set_alarm1(self, val):
        if val.upper() == "ON":
            self.set_val("27", "0001")
        elif val.upper() == "OFF":
            self.set_val("27", "0000")

    def get_alarm2(self):
        rval = self.get_val("5e0000")
        if rval[4] == b"1":
            return "ON"
        else:
            return "OFF"

    def set_alarm2(self, val):
        if val.upper() == "ON":
            self.set_val("2a", "0001")
        elif val.upper() == "OFF":
            self.set_val("2a", "0000")

    def get_sensor_type(self):
        rval = self.get_val("540000")
        if rval[4] == b"1":
            return "10K"
        else:
            return "15K"

    def set_sensor_type(self, val):
        if val.upper() == "10K":
            self.set_val("20", "0001")
        elif val.upper() == "15K":
            self.set_val("20", "0000")

    def get_control_mode(self):
        rval = self.get_val("550000")
        if rval[4] == b"1":
            return "HEATING"
        else:
            return "COOLING"

    def set_control_mode(self, val):
        if val.upper() == "COOLING":
            self.set_val("21", "0000")
        elif val.upper() == "HEATING":
            self.set_val("21", "0001")

    def get_low_set_range(self):
        return hexc2dec(self.get_val("560000"))

    def set_low_set_range(self, val):
        if val < 0:
            val += 2**16
        self.set_val("22", dec2hex(val))

    def get_high_set_range(self):
        return hexc2dec(self.get_val("570000"))

    def set_high_set_range(self, val):
        if val < 0:
            val += 2**16
        self.set_val("23", dec2hex(val))

    def get_offset(self):
        return hexc2dec(self.get_val("580000"))

    def set_offset(self, val):
        if val < 0:
            val += 2**16
        self.set_val("24", dec2hex(val))

    def get_alarm1_low(self):
        return hexc2dec(self.get_val("590000"))

    def set_alarm1_low(self, val):
        if val < 0:
            val += 2**16
        self.set_val("25", dec2hex(val))

    def get_alarm1_high(self):
        return hexc2dec(self.get_val("5a0000"))

    def set_alarm1_high(self, val):
        if val < 0:
            val += 2**16
        self.set_val("26", dec2hex(val))

    def get_alarm2_low(self):
        return hexc2dec(self.get_val("5c0000"))

    def set_alarm2_low(self, val):
        if val < 0:
            val += 2**16
        self.set_val("28", dec2hex(val))

    def get_alarm2_high(self):
        return hexc2dec(self.get_val("5d0000"))

    def set_alarm2_high(self, val):
        if val < 0:
            val += 2**16
        self.set_val("29", dec2hex(val))

    def get_alarm_latch_function(self):
        # 0: no latches
        # 1: alarm1 latch
        # 2: alarm2 latch
        # 3: alarm1 & alarm2 latch
        return self.get_val("5f0000")[4].decode("utf-8")

    def set_alarm_latch_function(self, val):
        self.set_val("2b", "0" * 3 + str(val))

    def get_alarm1_deadband(self):
        return hexc2dec(self.get_val("610000")) / 10.0

    def set_alarm1_deadband(self, val):
        self.set_val("2d", dec2hex(int(val * 10.0)))

    def get_alarm2_deadband(self):
        return hexc2dec(self.get_val("620000")) / 10.0

    def set_alarm2_deadband(self, val):
        self.set_val("2e", dec2hex(int(val * 10.0)))

    def get_analog_multiplier(self):
        return hexc2dec(self.get_val("630000")) / 100.0

    def set_analog_multiplier(self, val):
        self.set_val("2f", dec2hex(int(val * 100.0)))

    def get_output_enable(self):
        val = self.get_val("640000")[4].decode("utf-8")
        if val == "0":
            return "OFF"
        elif val == "1":
            return "ON"

    def set_output_enable(self, val):
        if val.upper() == "OFF":
            self.set_val("30", "0000")
        elif val.upper() == "ON":
            self.set_val("30", "0001")
