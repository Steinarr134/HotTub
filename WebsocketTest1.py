"""
This python script is serving the websocket.
It will be run in a seperate process and pipes will be used
to communicate with it. It will reacieve info about the HotTub's
state through the stdin pipe.
whenever a user opens a websocket (by loading the website) or
sends something through the socket (by pushing any button on the
website) this script will send the HotTub's last known state.

Anything recieved trough the websocket will be passed on to the
parent process through the stdout pipe.

"""


from autobahn.twisted.websocket import WebSocketServerProtocol, \
    WebSocketServerFactory
import threading
import sys
import select
import atexit
import socket

Current = '{"Type":"Current" , "InfoString":"BlaBlaBlaInfoSomethingC"}'
Request = '{"Type":"Request" , "AutoTemp":35 , "ManualTemp":37 , "ManualFlow":0 ,"ManualValve":false}'


def dprint(s):
    print(s)

HotTub_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
HotTub_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
HotTub_socket.bind(('', 12345))
HotTub_socket.listen(1)


class HotTubCommunicationThread(threading.Thread):
    def __init__(self, conn):
        threading.Thread.__init__(self)
        self.conn = conn
        self.Stop = False

    def run(self):
        dprint("HotTubCommunicationThread started")
        global Current
        while True:
            rfds, wfds, efds = select.select([self.conn], [], [], 1)
#            print(rfds)
            if rfds:
                incoming = rfds[0].recv(1024)
                dprint("HotTubCommunicationThread recieved: " + incoming)
                if incoming == '':
                    break
                else:
                    dprint("saved2current")
                    
                    Current = incoming
            if self.Stop:
                break

dprint("waiting for client")
HotTub_connection, client_address = HotTub_socket.accept()
dprint("a wild client appeared")

t = HotTubCommunicationThread(HotTub_connection)
t.start()


class MyServerProtocol(WebSocketServerProtocol):

    def onConnect(self, request):
        pass

    def onOpen(self):
        print "We got a client, sending:"
        print "   Current: " + Current
        print "   Request: " + Request
        self.sendMessage(Current)
        self.sendMessage(Request)

    def onMessage(self, payload, isBinary):
        dprint("onmessage received " + payload)
        dprint("sending " + Current + " to client")
        self.sendMessage(Current)
        global Request
        Request = payload
        try:
            HotTub_connection.send(payload)
            dprint("sent " + payload + " to HotTub")
        except socket.error as problem:
            print problem
            sys.exit()

    def onClose(self, wasClean, code, reason):
        pass


from twisted.python import log
from twisted.internet import reactor

# logfile = open('/home/pi/Documents/HotTub/WebsocketLog1.txt', 'w')  # uncomment!
#
# log.startLogging(logfile)

factory = WebSocketServerFactory(u"ws://localhost:8521") # breyta i 85.220.14.166
factory.protocol = MyServerProtocol
# factory.setProtocolOptions(maxConnections=2)


def cleanup():
    t.Stop = True

atexit.register(cleanup)

print("now serving port 8521")
reactor.listenTCP(8521, factory)
reactor.run()
print "We'll never get to this"
cleanup()
