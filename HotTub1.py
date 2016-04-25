import atexit
import json
from apscheduler.schedulers.background import BackgroundScheduler
import subprocess
import threading
import time
import select
import socket
from datetime import datetime
from MoteinoBeta import MoteinoNetwork
import logging
# from PID import PID
logging.basicConfig()

scheduler = BackgroundScheduler()
scheduler.start()


def dprint(*args):
    s = ""
    for a in args:
        s += str(a)
    print(s)


class State(object):
    """
    This class describes a state of the HotTub.
    It is also responsible for encoding and decoding itself to and
    from a json string.
    """
    def __init__(self, flag, temp=37, full=False):
        self.Temp = temp
        self.Full = full
        self.Flag = flag

    def __str__(self):
        return "HotTub State -> Temp: " + str(self.Temp) + "  Full: " + str(self.Full)

    def encode(self):
        return json.dumps({'Flag': self.Flag,
                           'Temp': self.Temp,
                           'Full': self.Full})
    
    def decode_and_become(self, payload):
        a = json.loads(payload)
        self.Temp = a['Temp'] + 1  # stilla thetta!
        self.Full = a['Full'] 


# Here we will set up the moteino network. Moteinos are arduino clones
# that have wireless capabilities. We will communicate with one
# trough a serial port and that one will send messages to the other
# ones.

# it is commented out because it is not in use as of yet

class MyNetwork(MoteinoNetwork):
    def __init__(self):
        MoteinoNetwork.__init__(self, port='/dev/ttyAMA0', baudrate=115200)
        
    def recieve(self, diction):  # overwrite this to respond
        print "mynetwork received: "
        print diction


# instantiate MyNetwork
mynetwork = MyNetwork()


class ReactFunThread(threading.Thread):
    """
    This is designed to run reactfun(incoming) in a seperate thread
    """
    def __init__(self, incoming, reactfun):
        threading.Thread.__init__(self)
        self.Incoming = incoming
        self.ReactFun = reactfun

    def run(self):
        self.ReactFun(self.Incoming)


class Listen2socketThread(threading.Thread):
    """
    This is a thread that listenes to listen2 with readline and
    then starts a thread that runs reactfun(incoming)
    """
    def __init__(self, sock, reactfun):
        threading.Thread.__init__(self)
        self.socket = sock
        self.ReactFun = reactfun
        self.Stop = False

    def run(self):
        dprint("Listen2socketThread started")

        while True:
            rfds, wfds, efds = select.select([self.socket], [], [], 1)
            # print(rfds)
            if rfds:
                incoming = rfds[0].recv(1024)
                dprint("listening thread recieved: " + incoming)
                if incoming == '':
                    break
                else:
                    t = ReactFunThread(incoming, self.ReactFun)
                    t.start()
            if self.Stop:
                break


def _add_one_time_job(func, after):
    scheduler.add_job(func, 'date',
                      run_date=datetime.fromtimestamp(time.time() + after))


# class HotTubController(object):
#     """I fear a PID would be too hard to properly tune.
#        Especially since the input temperature needed for
#        a desired final temperature is heavily dependent on
#        the outside temperature, wind, rain, etc.
#        Therefore I am going to try and implement some type
#        of controller that tries to calculate the heat loss
#        and prevent it.
#
#        We haven't tested this code and it isn't even complete.
#        Each test probably takes 2 hours and cost a lot of
#        water but hopefully we will test it in the summer.
#
#        """
#     def __init__(self, requested_temp):
#         self.Requested = requested_temp
#         self.history = list() # (flow, temp, time)
#         self.State = "filling"
#         self.LastTime = 0
#
#     class historic_event(object):
#         def __init__(self, flow, temp):
#             self.Flow = flow
#             self.Temp = temp
#             self.Time = time.time()
#
#     def add2history(self, flow, temp):
#         self.history.append(self.historic_event(flow, temp))
#
#     def compute(self, temp):
#         last = self.history[-1]
#         first = self.history[0]
#         elapsed_time = time.time() - self.LastTime
#         E_in_since_last = last.Temp*last.Flow*(time.time() - last.Time)
#         E_in_from_start = self.E_in_last + E_in_since_last
#         if self.State == 'filling':
#             E_now = self.water_pumped()*temp
#             E_lost_from_start = E_in_from_start - E_now
#             E_loss_per_time = E_lost_from_start/float(elapsed_time)
#             E_needed = self.E_final - E_now
#             E_needed_per_time = E_needed/float(self.filling_time - elapsed_time)
#             temp_out = E_needed_per_time*100
#             return (100, temp_out)
#         else:
#             E_out_since_last = last.Flow.temp*(time.time()-last.Time)
#             E_out_from_start = self.E_out_last + E_out_since_last
#             E_now = self.total_water*temp
#             E_lost_from_start = E_in_from_start - E_now - E_out_from_start
#             E_loss_per_time = E_lost_from_start/float(elapsed_time)
#             temp_out = E_loss_per_time/float(20)
#             if temp_out < self.max_temp:
#                return (20, temp_out)
#             else:
#                flow = E_loss_per_time/float(self.max_temp)
#                return (flow, self.max_temp)
                

class HotTub(object):
    """
    This is a class that defines the HotTub's behavior

    There should only be one instance of this class.    
    """
    def __init__(self, network, scheduler):
        self.Scheduler = scheduler
        self.Network = network
        self.CurrentState = State('current')
        self.RequestedState = State(temp=40, flag='request')

        # operating values:
        self.kP_Full = 10
        self.kP_Filling = 1
        self.MaintainTemp = 450
        self.FlowWhenCooling = 30

        # Start a socket that communicates with websocket server
        self.WSsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.WSsocket.connect(('', 12345))
        dprint("successfully connected to WS")

        # start a thread that listens to this socket
        self.WSlistener = Listen2socketThread(self.WSsocket, self.request)
        self.WSlistener.start()

        # wait a bit for socket stuff to start and then send current state
        time.sleep(0.2)
        self.send_current_state()
        
        # create Devices on the network
        self.Fosset = self.Network.add_device("Fosset",
                                              21,
                                              "int Command;" +
                                              "byte Flow;" +
                                              "int Temp;")
        self.UnderTub = self.Network.add_device("UnderTub",
                                                22,
                                                "int Command;" +
                                                "int PipeTemp;" +
                                                "int HotTubTemp;" +
                                                "int OutsideTemp;" + 
                                                "bool ValveIsOpen;" +
                                                "int OverflowTemp")
        # A dict for our commands to make code more readable
        self.Commands = {'Unfreeze': 2101,
                         'Regulate': 2102,
                         'Status': 99,
                         'Off': 2103,
                         'OpenValve': 2201,
                         'CloseValve': 2202}
        # I'm increasing max wait time to 5 seconds because nothing in
        # our system is time sensitive so It can be very long
        self.Network.max_wait = 5000

        self.LastRequest = str()
        self.LastRequestTime = time.time()
        self.RequestIgnoreTime = 20  # seconds

        self.RegulateJob = scheduler.add_job(self._regulate,
                                             'interval',
                                             seconds=15)
        self.RegulateJob.pause()

        self.UpdateCurrentJob = scheduler.add_job(self.update_current_state,
                                                  'interval',
                                                  minutes=5)

        self.PreventFreezingJob = scheduler.add_job(self.prevent_freezing,
                                                    'interval',
                                                    hours=2)
        self._OverflowTempThreshold = 250
        self.Flag_A = False

    def send_current_state(self):
        self.WSsocket.send(self.CurrentState.encode())

    def prevent_freezing(self):
        print "Here I come to save the day!... by preventing pipe freezing"
        d = self.UnderTub.send_and_receive({'Command': self.Commands['Status']})
        if not d:
            print "prevent_freezing <- UnderTub is not responding!!!"
        else:
            if d['OutsideTemp'] < 0:
                if d['PipeTemp'] < 20:
                    print "It's my time to shine! There'll be no pipe freezing today mister!"
                    if not d['ValveIsOpen']:
                        self.UnderTub.send({'Command': self.Commands['OpenValve']})
                    self.Fosset.send({'Command': self.Commands['Unfreeze']})
                    # sending unfreeze means it will send hot water through for 60 seconds

    def request(self, incoming):
        dprint("Request received: ", incoming)
        self.LastRequest = incoming
        self.LastRequestTime = time.time()
        time.sleep(self.RequestIgnoreTime + 0.1)
        if time.time() - self.LastRequestTime > self.RequestIgnoreTime:
            self.handle_request(incoming)
        
    def handle_request(self, incoming):
        self.RequestedState.decode_and_become(incoming)
        print "We are going for: " + str(self.RequestedState)
        if self.RequestedState.Full:
            self.UnderTub.send({'Command': self.Commands['CloseValve']})
            self.Fosset.send({'Command': self.Commands['Regulate'],
                              'Flow': 100,
                              'Temp': self.RequestedState.Temp*10})
            self.RegulateJob.resume()
            _add_one_time_job(self.empty, 60*60*4)  # in 4 hours
        else:
            self.empty()
            
    def empty(self):
        self.RequestedState.Full = False
        self.RegulateJob.pause()
        self.Fosset.send({'Command': self.Commands['Off']})
        self.UnderTub.send({'Command': self.Commands['OpenValve']})

    def update_current_state(self):
        d = self.UnderTub.send_and_receive({'Command': self.Commands['Status']})
        if d:
            self.CurrentState.Full = d['OverflowTemp'] > self._OverflowTempThreshold
            self.CurrentState.Temp = d['HotTubTemp']/float(10)
            self.send_current_state()
            return True
        else:
            print "update_current_state <- UnderTub not responding"
            return False

    def _start_regulating(self):
        # self.controller = HotTubController(self.RequestedState.Temp)
        self.Flag_A = True
        scheduler.add_job(self._regulate,
                          'interval',
                          id='HotTubRegulate',
                          replace_existing=True,
                          seconds=30)

    def _regulate(self):
        print "regulating..."
        success = self.update_current_state()
        if success:
            if self.CurrentState.Full and self.Flag_A:
                success = self.Fosset.send({'Command': self.Commands['Regulate'],
                                            'Flow': 20,
                                            'Temp': self.RequestedState.Temp})
                if success:
                    self.Flag_A = False
                    print "I changed things to slower flow and such"
            else:
                print "things are A-ok!"

    #    success = self.update_current_state()
    #    if success:
    #        (flow, temp) =  self.Controller.compute()
    #        success = self.Fosset.send({'Command': self.Commands['Regulate'],
    #                                    'Flow': flow,
    #                                    'Temp': temp})
    #        if success:
    #            self.controller.add2history(flow, temp)
    #
    #
    # def regulate(self):
    #    print "Im Regulating!"
    #    if not self.RequestedState.Full:
    #        print("Wait I'm not supposed to regulate when I'm not" +
    #              " trying to become Full!!!")
    #    else:
    #        dprint("flag1")
    #        self.update_current_state()
    #        dprint("flag2")
    #        if self.CurrentState.Full:
    #            diff = self.RequestedState.Temp - self.CurrentState.Temp
    #            output = diff*self.kP_Full
    #            dprint("HotTub is full, diff: ", diff, "and output: ", output)
    #            if output >= -10:
    #                temp = self.MaintainTemp
    #                flow = output / temp
    #            else:
    #                flow = self.FlowWhenCooling
    #                temp = output / flow
    #        else:
    #            dprint("HotTub is filling up")
    #            flow = 100  # flow is still fully on
    #            diff = self.RequestedState.Temp - self.CurrentState.Temp
    #            temp = diff*self.kP_Filling
    #            dprint("setting:: flow: ", flow, " and temp: ", temp)
    #
    #
    #        # and then we send temp and flow
    #        self.Fosset.send({'Command': self.Commands['Regulate'],
    #                          'Flow': flow,
    #                          'Temp': temp})
hottub = HotTub(mynetwork, scheduler)


def cleanup():
    hottub.WSlistener.Stop = True
    print "cleanup is done (hopefully)"
    # some other cleanup needed?

atexit.register(cleanup)

# The system is now completely set up and we'll do nothing forever

time.sleep(1000)

# If we make it past that while loop than the system will exit
