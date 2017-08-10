"""
Library to communicate with the Naze32 flight control board.
Receives telemetry data: angx, angy and heading
Transmits attitude commands: roll, pitch, yaw
"""

from __future__ import division
from __future__ import print_function
import time
import struct
import os
import serial
import Adafruit_PCA9685
import pigpio

# identifiers
MSP_IDENT = 100
MSP_STATUS = 101
MSP_RAW_IMU = 102
MSP_SERVO = 103
MSP_MOTOR = 104
MSP_RC = 105
MSP_RAW_GPS = 106
MSP_COMP_GPS = 107
MSP_ATTITUDE = 108
MSP_ALTITUDE = 109
MSP_ANALOG = 110
MSP_RC_TUNING = 111
MSP_PID = 112
MSP_BOX = 113
MSP_MISC = 114
MSP_MOTOR_PINS = 115
MSP_BOXNAMES = 116
MSP_PIDNAMES = 117
MSP_WP = 118
MSP_BOXIDS = 119
MSP_RC_RAW_IMU = 121
MSP_SET_RAW_RC = 200
MSP_SET_RAW_GPS = 201
MSP_SET_PID = 202
MSP_SET_BOX = 203
MSP_SET_RC_TUNING = 204
MSP_ACC_CALIBRATION = 205
MSP_MAG_CALIBRATION = 206
MSP_SET_MISC = 207
MSP_RESET_CONF = 208
MSP_SET_WP = 209
MSP_SWITCH_RC_SERIAL = 210
MSP_IS_SERIAL = 211
MSP_EEPROM_WRITE = 250
MSP_DEBUG = 254

# payload byte lengths
# None means not implemented yet
MSP_PAYLOAD_LEN = {
    MSP_IDENT : 7,
    MSP_STATUS : 11,
    MSP_RAW_IMU : 18,
    MSP_SERVO : None,
    MSP_MOTOR : None,
    MSP_RC : 16,
    MSP_RAW_GPS : 14,
    MSP_COMP_GPS : 5,
    MSP_ATTITUDE : 6,
    MSP_ALTITUDE : 6,
    MSP_ANALOG : 7,
    MSP_RC_TUNING : 7,
    MSP_PID : None,
    MSP_BOX : None,
    MSP_MISC : None,
    MSP_MOTOR_PINS : None,
    MSP_BOXNAMES : None,
    MSP_PIDNAMES : None,
    MSP_WP : 18,
    MSP_BOXIDS : None,
    MSP_RC_RAW_IMU : None,
    MSP_SET_RAW_RC : 16,
    MSP_SET_RAW_GPS : 14,
    MSP_SET_PID : None,
    MSP_SET_BOX : None,
    MSP_SET_RC_TUNING : 7,
    MSP_ACC_CALIBRATION : 0,
    MSP_MAG_CALIBRATION : 0,
    MSP_SET_MISC : None,
    MSP_RESET_CONF : 0,
    MSP_SET_WP : 18,
    MSP_SWITCH_RC_SERIAL : None,
    MSP_IS_SERIAL : None,
    MSP_EEPROM_WRITE : 0,
    MSP_DEBUG : None
}

# payload format strings
# None means not implemented yet
MSP_PAYLOAD_FMT = {
    MSP_IDENT : '<BBBI',
    MSP_STATUS : '<HHHIB',
    MSP_RAW_IMU : '<9h',
    MSP_SERVO : None,
    MSP_MOTOR : None,
    MSP_RC : '<8H',
    MSP_RAW_GPS : '<BBIIHHH',
    MSP_COMP_GPS : None,
    MSP_ATTITUDE : '<3h',
    MSP_ALTITUDE : '<ih',
    MSP_ANALOG : '<BHHH',
    MSP_RC_TUNING : '<BBBBBBB',
    MSP_PID : None,
    MSP_BOX : None,
    MSP_MISC : None,
    MSP_MOTOR_PINS : None,
    MSP_BOXNAMES : None,
    MSP_PIDNAMES : None,
    MSP_WP : '<BIIIHHB',
    MSP_BOXIDS : None,
    MSP_RC_RAW_IMU : None,
    MSP_SET_RAW_RC : '<8H',
    MSP_SET_RAW_GPS : '<BBIIHHH',
    MSP_SET_PID : None,
    MSP_SET_BOX : None,
    MSP_SET_RC_TUNING : '<BBBBBBB',
    MSP_ACC_CALIBRATION : '',
    MSP_MAG_CALIBRATION : '',
    MSP_SET_MISC : None,
    MSP_RESET_CONF : '',
    MSP_SET_WP : '<BIIIHHB',
    MSP_SWITCH_RC_SERIAL : None,
    MSP_IS_SERIAL : None,
    MSP_EEPROM_WRITE : '',
    MSP_DEBUG : None
}

class MultiWii(object):
    """Handle Multiwii Serial Protocol

    In the Multiwii serial protocol (MSP), packets are sent serially to and from
    the flight control board.
    Data is encoded in bytes using the little endian format.

    Packets consist of
        Header   (3 bytes)
        Size     (1 byte)
        Type     (1 byte)
        Payload  (size indicated by Size portion of packet)
        Checksum (1 byte)

    Header is composed of 3 characters (bytes):
        byte 0: '$'
        byte 1: 'M'
        byte 2: '<' for data going to the flight control board or
                '>' for data coming from the flight contorl board

    Size is the number of bytes in the Payload
        Size can range from 0-255
        0 indicates no payload

    Type indicates the type (i.e. meaning) of the message
        Types values and meanings are mapped with MultiWii class variables

    Payload is the packet data
        Number of bytes must match the value of Size
        Specific formatting is specific to each Type

    Checksum is the XOR of all of the bits in [Size, Type, Payload]
    """
    def __init__(self, serPort):
        self.attitude = {'angx':0, 'angy':0, 'heading':0}
        self.altitude = {'estalt':0, 'vario':0}
        self.pid_coef = {
            'rp':0, 'ri':0, 'rd':0,
            'pp':0, 'pi':0, 'pd':0,
            'yp':0, 'yi':0, 'yd':0}
        self.rc_channels = {'roll':0, 'pitch':0, 'yaw':0, 'throttle':0}
        self.raw_imu = {
            'ax':0, 'ay':0, 'az':0,
            'gx':0, 'gy':0, 'gz':0,
            'mx':0, 'my':0, 'mz':0}
        self.motor = {'m1':0, 'm2':0, 'm3':0, 'm4':0}

        self.ser = serial.Serial()
        self.ser.port = serPort
        self.ser.baudrate = 115200
        self.ser.bytesize = serial.EIGHTBITS
        self.ser.parity = serial.PARITY_NONE
        self.ser.stopbits = serial.STOPBITS_ONE
        self.ser.timeout = None
        self.ser.xonxoff = False
        self.ser.rtscts = False
        self.ser.dsrdtr = False
        self.ser.writeTimeout = 2
        try:
            self.ser.open()
        except(Exception) as error:
            print("\n\nError opening port "+self.ser.port +":")
            print(str(error)+"\n\n")
            raise error

    @staticmethod
    def compute_checksum(packet):
        """Computes the MSP checksum

        Input
        -----
        packet: MSP packet without checksum created using struct.pack
        """
        checksum = 0
        for i in packet[3:].decode():
            checksum ^= ord(i)
        return checksum

    def send_msg(self, data_length, msg_type, data, data_format):
        """Send a message to the flight control board

        Inputs
        ------
        data_length: int
            length, in bytes, of the payload data
        msg_type: int
            message type identifier
            specified as one of the class variables
        data: list of data items
            data list contents specific to the message type
        data_format: string
            formatting string to use by struct.pack to pack data into packet
            mapped in class variable MSP_PAYLOAD_FMT
        """
        packet = (
            struct.pack('<ccc', b'$', b'M', b'<') +
            struct.pack('<BB', data_length, msg_type) +
            struct.pack(data_format, *data))
        packet += struct.pack('<B', self.compute_checksum(packet))
        try:
            self.ser.write(packet)
        except(Exception) as error:
            print("\n\nError sending command on port " + self.ser.port)
            print(str(error) + "\n\n")
            raise error

    def arm(self):
        """Arms the motors"""
        timer = 0
        start = time.time()
        while timer < 0.5:
            data = [1500, 1500, 2000, 1000]
            self.send_msg(
                8, MSP_SET_RAW_RC, data,
                MSP_PAYLOAD_FMT[MSP_SET_RAW_RC])
            time.sleep(0.05)
            timer = timer + (time.time() - start)
            start = time.time()

    def disarm(self):
        """Disarms the motors"""
        timer = 0
        start = time.time()
        while timer < 0.5:
            data = [1500, 1500, 1000, 1000]
            self.send_msg(
                8, MSP_SET_RAW_RC, data, MSP_PAYLOAD_FMT[MSP_SET_RAW_RC])
            time.sleep(0.05)
            timer = timer + (time.time() - start)
            start = time.time()

    def set_pid(self, pid_coeff):
        """Set the PID coefficients"""
        raise NotImplementedError

    def get_data(self, cmd):
        """Function to request and receive a data packet from the board

        Inputs
        ------
        cmd : int
            command as defined by the MSP_* identifiers

        Outputs
        -------
        data : list
            data decoded from serial stream according to MSP protocol
        """
        try:
            self.send_msg(0, cmd, [], '')
            header = self.ser.read(5).decode() # [$, M, {<, >}, size, type]
            datalength = ord(header[3])
            msg_type = ord(header[4])
            # check that message received matches expected message
            assert msg_type == cmd, "Unexpected MSP message type detected"
            buf = self.ser.read(datalength)
            data = struct.unpack(MSP_PAYLOAD_FMT[cmd], buf)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except(Exception) as error:
            print("\n\nError in getData on port "+self.ser.port)
            print(str(error)+"\n\n")
            raise error
        return data

    def get_attitude(self):
        """Get the attitude data"""
        data = self.get_data(MSP_ATTITUDE)
        self.attitude['angx'] = float(data[0]/10.0)
        self.attitude['angy'] = float(data[1]/10.0)
        self.attitude['heading'] = float(data[2])
        return self.attitude

    def get_altitute(self):
        """Get the altitude data"""
        data = self.get_data(MSP_ALTITUDE)
        self.altitude['estalt'] = float(data[0])
        self.altitude['vario'] = float(data[1])
        return self.altitude

    def get_rc(self):
        """Get the rc data"""
        data = self.get_data(MSP_RC)
        self.rc_channels['roll'] = data[0]
        self.rc_channels['pitch'] = data[1]
        self.rc_channels['yaw'] = data[2]
        self.rc_channels['throttle'] = data[3]
        return self.rc_channels

    def get_raw_imu(self):
        """Get the raw imu data"""
        data = self.get_data(MSP_RAW_IMU)
        self.raw_imu['ax'] = float(data[0])
        self.raw_imu['ay'] = float(data[1])
        self.raw_imu['az'] = float(data[2])
        self.raw_imu['gx'] = float(data[3])
        self.raw_imu['gy'] = float(data[4])
        self.raw_imu['gz'] = float(data[5])
        self.raw_imu['mx'] = float(data[6])
        self.raw_imu['my'] = float(data[7])
        self.raw_imu['mz'] = float(data[8])
        return self.raw_imu

    def get_motor(self):
        """Get the motor data"""
        data = self.get_data(MSP_MOTOR)
        self.motor['m1'] = float(data[0])
        self.motor['m2'] = float(data[1])
        self.motor['m3'] = float(data[2])
        self.motor['m4'] = float(data[3])
        return self.motor

    def get_pid_coeff(self):
        """Get the PID coefficients"""
        data = self.get_data(MSP_PID)
        data_pid = []
        for data_val in data:
            data_pid.append(data_val%256)
            data_pid.append(data_val//256)
        for idx in [0, 3, 6, 9]:
            data_pid[idx] = data_pid[idx]/10.0
            data_pid[idx+1] = data_pid[idx+1]/1000.0
        self.pid_coef['rp'] = data_pid[0]
        self.pid_coef['ri'] = data_pid[1]
        self.pid_coef['rd'] = data_pid[2]
        self.pid_coef['pp'] = data_pid[3]
        self.pid_coef['pi'] = data_pid[4]
        self.pid_coef['pd'] = data_pid[5]
        self.pid_coef['yp'] = data_pid[6]
        self.pid_coef['yi'] = data_pid[7]
        self.pid_coef['yd'] = data_pid[8]
        return self.pid_coef

    def close_serial(self):
        """Close the serial port and reset the stty settings"""
        self.ser.close()
        bash_cmd = "stty sane < /dev/ttyUSB0"
        os.system(bash_cmd)

class DroneComm(object):
    """Handles communication to and from the drone.

    Receives data over the USB with Multiwii protocol
    Transmits data via an I2C interface to an Adafruit PWM generator

    Paramters
    ---------
    pwm_ctrl: bool
        enable pwm control (default True)
    period: float
        pwm period (default 22ms)
    k_period: float
        pwm period calibration factor
    roll_pwm_trim: int
        roll channel trim (us)
    pitch_pwm_trim: int
        pitch channel trim (us)
    yaw_pwm_trim: int
        yaw channel trim (us)
    port: string
        usb port attached to flight control board (default "/dev/ttyUSB0")
        if None, assumes no input connection from flight control board
    """
    # Range of Values (Pulse Width): 1.1ms -> 1.9ms
    MIN_WIDTH = 0.0011
    MID_WIDTH = 0.0015
    MAX_WIDTH = 0.0019

    # Max change in pulse width from mid posision: 0.4ms
    MAX_DELTA_PWIDTH = 0.0004

    # time precision of feather pwm signal
    # each pwm cycle is divided into TICKS units of time
    TICKS = 4096

    # Featherboard channel map
    ROLL_CHANNEL = 3
    PITCH_CHANNEL = 2
    YAW_CHANNEL = 1
    THR_CHANNEL = 0

    # Calibration factor to compensate for mismatch between
    # requested pwm period and pwm freq implemented by Adafruit PWM generator
    # Useage:
    #     requested_period = K_PWM * target_period
    # when requesting a PWM signal with period target_period
    DEFAULT_K_PERIOD = 0.023 / 0.022 # 23ms/22ms

    def __init__(
            self, pwm_ctrl=True,
            period=0.022, k_period=None,
            roll_pwm_trim=0, pitch_pwm_trim=0, yaw_pwm_trim=0,
            port="/dev/ttyUSB0"):
        self.period = period

        # store trims in units of seconds
        self.roll_pwm_trim = roll_pwm_trim * 1E-6
        self.pitch_pwm_trim = pitch_pwm_trim * 1E-6
        self.yaw_pwm_trim = yaw_pwm_trim * 1E-6

        if k_period is None:
            k_period = self.DEFAULT_K_PERIOD

        if pwm_ctrl:
            self.pwm = Adafruit_PCA9685.PCA9685()
            self.pwm.set_pwm_freq(1./(k_period*period))
            self.reset_channels()
        else:
            self.pwm = None

        if port is None:
            self.board = None
        else:
            self.board = MultiWii(port)

    def reset_channels(self):
        """Reset channels 0-6 on the feather board

        Applies trim to roll/pitch/yaw channels
        """
        for i in range(6):
            self.set_pwidth(i, self.MID_WIDTH)
        self.set_pwidth(
            self.ROLL_CHANNEL, self.MID_WIDTH + self.roll_pwm_trim)
        self.set_pwidth(
            self.PITCH_CHANNEL, self.MID_WIDTH + self.pitch_pwm_trim)
        self.set_pwidth(
            self.YAW_CHANNEL, self.MID_WIDTH + self.yaw_pwm_trim)

    def set_pwidth(self, channel, width):
        """Set a positive Pulse Width on a channel

        Parameters
        ----------
        channel: int
            pwm channel to set positive pulse width
        width: float
            positive pulse width (seconds)
        """
        width = width / self.period * self.TICKS
        pulse = int(round(width))
        self.pwm.set_pwm(channel, 0, pulse)

    def set_roll_pwidth(self, width):
        """Apply trim and set the pwm Roll signal's positive pulse width

        Parameters
        ----------
        width: float
            positive pulse width (seconds)
        """
        # apply trim offset
        width += self.roll_pwm_trim
        width, valid = self.validate_pwidth(width)
        self.set_pwidth(self.ROLL_CHANNEL, width)
        if not valid:
            print("WARNING: Requested roll pwidth out of range!")

    def set_pitch_pwidth(self, width):
        """Apply trim and set the pwm Pitch signal's positive pulse width

        Parameters
        ----------
        width: float
            positive pulse width (seconds)
        """
        # apply trim offset
        width += self.pitch_pwm_trim
        width, valid = self.validate_pwidth(width)
        self.set_pwidth(self.PITCH_CHANNEL, width)
        if not valid:
            print("WARNING: Requested pitch pwidth out of range!")

    def set_yaw_pwidth(self, width):
        """Apply trim and set the pwm Yaw signal's positive pulse width

        Parameters
        ----------
        width: float
            positive pulse width (seconds)
        """
        # apply trim offset
        width += self.yaw_pwm_trim
        width, valid = self.validate_pwidth(width)
        self.set_pwidth(self.YAW_CHANNEL, width)
        if not valid:
            print("WARNING: Requested yaw pwidth out of range!")

    def set_thr_pwidth(self, width):
        """Apply trim and set the pwm Throttle signal's positive pulse width

        Parameters
        ----------
        width: float
            positive pulse width (seconds)
        """
        # apply trim offset
        valid = True
        if width > self.MAX_WIDTH:
            valid = False
            width = self.MAX_WIDTH

        self.set_pwidth(self.THR_CHANNEL, width)
        if not valid:
            print("WARNING: Requested thr pwidth out of range!")

    def validate_pwidth(self, width):
        """Validate the pwm signal's positive pulse width

        Checks that the width is within the accepted range
        If not, the MAX_WIDTH or MIN_WIDTH is returned
        """
        if width > self.MAX_WIDTH:
            return self.MAX_WIDTH, False
        elif width < self.MIN_WIDTH:
            return self.MIN_WIDTH, False
        else:
            return width, True

    def set_roll_rate(self, rate):
        """Set the Roll rate

        Parameters
        ----------
        width: float [-1, 1]
            rate (scaled by max rate)
        """
        rate, valid = self.validate_rate(rate)
        width = (
            self.MID_WIDTH + self.roll_pwm_trim + rate*self.MAX_DELTA_PWIDTH)
        self.set_pwidth(self.ROLL_CHANNEL, width)
        if not valid:
            print("WARNING: Requested roll rate out of range!")

    def set_pitch_rate(self, rate):
        """Set the Pitch rate

        Parameters
        ----------
        width: float [-1, 1]
            rate (scaled by max rate)
        """
        rate, valid = self.validate_rate(rate)
        width = (
            self.MID_WIDTH + self.pitch_pwm_trim + rate*self.MAX_DELTA_PWIDTH)
        self.set_pwidth(self.PITCH_CHANNEL, width)
        if not valid:
            print("WARNING: Requested pitch rate out of range!")

    def set_yaw_rate(self, rate):
        """Set the Yaw rate

        Parameters
        ----------
        width: float [-1, 1]
            rate (scaled by max rate)
        """
        rate, valid = self.validate_rate(rate)
        width = (
            self.MID_WIDTH + self.yaw_pwm_trim + rate*self.MAX_DELTA_PWIDTH)
        self.set_pwidth(self.YAW_CHANNEL, width)
        if not valid:
            print("WARNING: Requested yaw rate out of range!")

    @staticmethod
    def validate_rate(rate):
        """Validate the requested channel rate is valid

        Checks that the width is within [-1, 1]
        Clips to range limit
        """
        if rate > 1:
            return 1, False
        elif rate < -1:
            return -1, False
        else:
            return rate, True

    def update_attitude(self):
        """Update the attitude data from the flight controller"""
        self.board.get_attitude()

    def update_imu(self):
        """Updates the IMU data from the flight controller"""
        self.board.get_raw_imu()

    def get_roll(self):
        """Returns the roll angle"""
        return self.board.attitude["angx"]

    def get_pitch(self):
        """Returns the pitch angle"""
        return self.board.attitude["angy"]

    def get_yaw(self):
        """Returns the yaw angle"""
        return self.board.attitude["heading"]

    def get_ax(self):
        """Returns the x acceleration"""
        return self.board.raw_imu["ax"]

    def get_ay(self):
        """Returns the y acceleration"""
        return self.board.raw_imu["ay"]

    def get_az(self):
        """Returns the z acceleration"""
        return self.board.raw_imu["az"]

    def get_droll(self):
        """Returns the roll angular velocity"""
        return self.board.raw_imu["gx"]

    def get_dpitch(self):
        """Returns the pitch angular velocity"""
        return self.board.raw_imu["gy"]

    def get_dyaw(self):
        """Returns the yaw angular velocity"""
        return self.board.raw_imu["gz"]

    def exit(self):
        """
        Used to gracefully exit and close the serial port
        """
        if self.pwm is not None:
            self.reset_channels()
        if self.board is not None:
            self.board.close_serial()

    def control_example(self):
        """
        Sets the Roll/Pitch/Yaw on the Naze32 flight controller
        to maximum then minimum pulse widths
        """
        self.reset_channels()
        time.sleep(1)

        self.set_yaw_pwidth(self.MAX_WIDTH)
        self.set_pitch_pwidth(self.MAX_WIDTH)
        self.set_roll_pwidth(self.MAX_WIDTH)

        time.sleep(2)

        self.set_yaw_pwidth(self.MIN_WIDTH)
        self.set_pitch_pwidth(self.MIN_WIDTH)
        self.set_roll_pwidth(self.MIN_WIDTH)

        time.sleep(2)
        self.reset_channels()

class Reader:
    """A class to read PWM pulses and calculate their frequency
    and duty cycle.  The frequency is how often the pulse
    happens per second.  The duty cycle is the percentage of
    pulse high time per cycle.
    """
    def __init__(self, rpi, gpio, weighting=0.0):
        """
        Instantiate with the Pi and gpio of the PWM signal
        to monitor.

        Optionally a weighting may be specified.  This is a number
        between 0 and 1 and indicates how much the old reading
        affects the new reading.  It defaults to 0 which means
        the old reading has no effect.  This may be used to
        smooth the data.
        """
        self.rpi = rpi
        self.gpio = gpio

        if weighting < 0.0:
            weighting = 0.0
        elif weighting > 0.99:
            weighting = 0.99

        self._new = 1.0 - weighting # Weighting for new reading.
        self._old = weighting       # Weighting for old reading.

        self._high_tick = None
        self._period = None
        self._high = None

        rpi.set_mode(gpio, pigpio.INPUT)

        self._cb = rpi.callback(gpio, pigpio.EITHER_EDGE, self._cbf)

    def _cbf(self, gpio, level, tick):
        """Callback function to trigger when level changes"""
        if level == 1:
            if self._high_tick is not None:
                t_diff = pigpio.tickDiff(self._high_tick, tick)
                if self._period is not None:
                    self._period = self._old*self._period + self._new*t_diff
                else:
                    self._period = t_diff
            self._high_tick = tick
        elif level == 0:
            if self._high_tick is not None:
                t_diff = pigpio.tickDiff(self._high_tick, tick)
                if self._high is not None:
                    self._high = self._old*self._high + self._new*t_diff
                else:
                    self._high = t_diff

    def frequency(self):
        """
        Returns the PWM frequency.
        """
        if self._period is not None:
            return 1000000.0 / self._period
        else:
            return 0.0

    def pulse_width(self):
        """
        Returns the PWM pulse width in microseconds.
        """
        if self._high is not None:
            return self._high / 1000000
        else:
            return 0.0

    def duty_cycle(self):
        """
        Returns the PWM duty cycle percentage.
        """
        if self._high is not None:
            return 100.0 * self._high / self._period
        else:
            return 0.0

    def cancel(self):
        """
        Cancels the reader and releases resources.
        """
        self._cb.cancel()