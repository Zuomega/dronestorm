import RPi.GPIO as GPIO
import time, sys, redis, pigpio
from dronestorm import DroneComm
from dronestorm import Reader

host = '127.0.0.1'
r = redis.StrictRedis(host=host)
drone = DroneComm()

FRONT_TRIG_ID = 12
FRONT_ECHO_ID = 16

BACK_TRIG_ID = 23
BACK_ECHO_ID = 24

YAW_CHN = 27
ROLL_CHN = 22
PITCH_CHN = 17
AUX1_CHN = 26
THR_CHN = 13

# Proportion coefficients: how strongly the error should be corrected
K_roll  = 4 * 1./180.
K_pitch = 4 * 1./90.

# Start program by placing drone on a flat surface to ensure accurate
# calibration Values
desired_roll = 0.
desired_pitch = 0.

pi = pigpio.pi()
ro = Reader(pi, ROLL_CHN)
p = Reader(pi, PITCH_CHN)
y = Reader(pi, YAW_CHN)
th = Reader(pi, THR_CHN)
aux = Reader(pi, AUX1_CHN)
time.sleep(0.1)

def init_HCSRO4_Sonar(TRIG_ID, ECHO_ID):
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(TRIG_ID, GPIO.OUT)
    GPIO.setup(ECHO_ID, GPIO.IN)

    GPIO.output(TRIG_ID, False)

    print("Init Sonar...")
    time.sleep(1)

def measureDistance_HCSRO4(TRIG_ID, ECHO_ID):
    GPIO.output(TRIG_ID, True)
    time.sleep(0.00001)
    GPIO.output(TRIG_ID, False)

    while GPIO.input(ECHO_ID) == 0:
      pulse_start = time.time()

    while GPIO.input(ECHO_ID) == 1:
      pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    distance = round(pulse_duration * 17150, 2)

    return distance

def measurePWM(pigpio_pulse):
    return pigpio_pulse.pulse_width()

init_HCSRO4_Sonar(FRONT_TRIG_ID, FRONT_ECHO_ID)
init_HCSRO4_Sonar(BACK_TRIG_ID, BACK_ECHO_ID)

try:
    while (True):
        front_dist = measureDistance_HCSRO4(FRONT_TRIG_ID, FRONT_ECHO_ID)
        back_dist = measureDistance_HCSRO4(BACK_TRIG_ID, BACK_ECHO_ID)

        desired_distance = 100. # cm
        K_front = 0.0004 / 100 # proportion constant
        K_back = -0.0004 / 100

        yaw = measurePWM(y)
        pitch = measurePWM(p)
        roll = measurePWM(ro)
        thr = measurePWM(th)
        aux1 = measurePWM(aux)


        # if (roll > 0.00149 and roll < 0.00152) or (pitch > 0.00149 and pitch < 0.00152) or (yaw > 0.00149 and yaw < 0.00152):
        #     # stabilize
        #
        #     drone.update_attitude()
        #
        #     curr_roll = drone.get_roll()
        #     curr_pitch = drone.get_pitch()
        #
        #     # Error between desired and actual roll/pitch
        #     error_roll =  desired_roll - curr_roll
        #     error_pitch = desired_pitch - curr_pitch
        #
        #     output_roll = K_roll * error_roll
        #     output_pitch = K_pitch * error_pitch
        #
        #     r.set('a_roll', output_roll)
        #     r.set('a_pitch', output_pitch)
        #     r.set('a_yaw', yaw)
        #     r.set('a_thr', thr)
        #     r.set('a_aux1', aux1)
        #
        # else:

        # manual control
        r.set('a_roll', roll)
        r.set('a_pitch', pitch)
        r.set('a_yaw', yaw)
        r.set('a_thr', thr)
        r.set('a_aux1', aux1)

        if (front_dist <= desired_distance) and (back_dist <= desired_distance):
            drone.update_attitude()

            curr_roll = drone.get_roll()
            curr_pitch = drone.get_pitch()

            # Error between desired and actual roll/pitch
            error_roll =  desired_roll - curr_roll
            error_pitch = desired_pitch - curr_pitch

            output_roll = K_roll * error_roll
            output_pitch = K_pitch * error_pitch

            r.set('a_roll', output_roll)
            r.set('a_pitch', output_pitch)
            r.set('a_yaw', yaw)
            r.set('a_thr', thr)
            r.set('a_aux1', aux1)

        elif (front_dist <= desired_distance):
            output_pwidth = K_front * front_dist + 0.0011

            # set corrective rate
            pitch = output_pwidth
            r.set('a_pitch', output_pwidth)

        elif (back_dist <= desired_distance):
            output_pwidth = K_back * back_dist + 0.0019

            # set corrective rate
            pitch = output_pwidth
            r.set('a_pitch', output_pwidth)



        acyaw = float(r.get('a_yaw'))
        acpitch = float(r.get('a_pitch'))
        acroll = float(r.get('a_roll'))
        acthr = float(r.get('a_thr'))
        acaux1 = float(r.get('a_aux1'))

        sys.stdout.write(
            "roll:%.5f pitch:%.5f yaw:%.5f thr:%.5f aux1:%.5f Front Distance:%4.2f Back Distance:%4.2f\r"%
            (acroll, acpitch, acyaw, acthr, acaux1, front_dist, back_dist))

        sys.stdout.flush()

except (KeyboardInterrupt, SystemExit):
    ro.cancel()
    p.cancel()
    y.cancel()
    aux.cancel()
    th.cancel()
    pi.stop()
    GPIO.cleanup()
