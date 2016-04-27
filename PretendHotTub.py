import socket
import threading
import sys

class Listen2socketThread(threading.Thread):
    """
    This is a thread that listenes to listen2 with readline and
    then starts a thread that runs reactfun(incoming)
    """
    def __init__(self, sock):
        threading.Thread.__init__(self)
        self.S = sock
        self.Stop = False

    def run(self):
        while True:
            incoming = self.S.recv(1024)
            print "received: " + incoming

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("localhost", 12345))

while True:
    a = sys.stdin.readline()[:-1]
    print "sending: " + a
    s.send(a)
