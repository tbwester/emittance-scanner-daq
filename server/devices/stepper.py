import serial
import time
import Queue

from devices.serial_com import fast_read

class Stepper():
    def __init__(self, port, debug=False):

        self._terminate = False
        self._debug = debug

        self._current_value = -1.
        self._error_code = 0
        self._max_value = None
        self._min_value = None

        self._line_ending = '\r'

        # startup commands
        self._init_prgm = [
            'FD',           # reset to default settings
            'MS=16',        # 16 microsteps/step
            'A=50000',      # steps/sec^2
            'VA SP=12800',  # create and set speed variable in steps/sec
            'VM=12800',     # maximum velocity in steps/sec
            'RC=85',        # set run current as percent (e.g. 75=75%)
            'S1=3,1',       # enable limit - switch & use with HM command
            'S2=2,1'        # enable limit + switch & use with HM command
        ]

        # loop commands - get current position
        self._run_prgm = [
            'PR C1 " " ER', 'r'
        ]

        # server will put commands to be issued in this queue object
        self._command_queue = Queue.Queue()

        self._s = serial.Serial(port, 9600)

        self._s.reset_input_buffer()
        self._s.reset_output_buffer()

    @property
    def current_value(self):
        return self._current_value

    @property
    def error_code(self):
        return self._error_code

    def run(self):
        time.sleep(0.1)
        for cmd in self._init_prgm:
            if self._debug:
                print(cmd)
            self._s.write(cmd + self._line_ending)

            time.sleep(1.0)

        #self._s.reset_input_buffer()
        #self._s.reset_output_buffer()
        time.sleep(1.0)
        print('Stepper ready')
        while not self._terminate:
            # check if we have outstanding commands in the queue

            if not self._command_queue.empty():
                cmd = self._command_queue.get_nowait()
                if self._debug:
                    print(cmd)
                self._s.write(cmd + self._line_ending)
                # call this because stepper echoes each command
                continue

            # otherwise do our regular loop
            for cmd in self._run_prgm:
                if self._debug:
                    print(cmd)
                if cmd != 'r':
                    self._s.write(cmd + self._line_ending)
                else:
                    # stepper echoes command, then prints newline
                    # so we have to read in some lines before actually getting
                    # the value. Unfortunately this is not predictable, so
                    # we just iterate reading until we find a value
                    gotResp = False
                    tries = 0
                    while not gotResp and tries < 5:
                        resp = fast_read(self._s).strip()
                        if self._debug:
                            print(resp)
                        try:
                            pos, err = (int(_) for _ in resp.split(' '))
                            self._current_value = float(pos)
                            gotResp = True
                            skip = False

                            # if we were previously at lower limit switch and moved up, reset error
                            if self._min_value is not None:
                                if pos > self._min_value:
                                    self._min_value = None
                                    self._error_code = 0
                                    skip = True

                            # if we were previously at lower limit switch and moved up, reset error
                            if self._max_value is not None:
                                if pos < self._max_value:
                                    self._max_value = None
                                    self._error_code = 0
                                    skip = True

                            if err == 83 and not skip:
                                # triggered upper limit switch. Register the error and reset error code for next command
                                self._max_value = pos
                                self._error_code = 83
                                self._command_queue.put('ER 0')
                            elif err == 84 and not skip:
                                # triggered lower limit switch
                                self._min_value = pos
                                self._error_code = 84
                                self._command_queue.put('ER 0')

                        except ValueError:
                            tries += 1

    def add_command_to_queue(self, cmd):
        self._command_queue.put(cmd)

    def terminate(self):
        self._terminate = True
