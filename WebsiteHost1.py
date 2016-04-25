"""
This script is serving the website.
"""

import socket
import select


HOST, PORT = '', 800

# Configure the socket
listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listen_socket.bind((HOST, PORT))
listen_socket.listen(1)

# retrieve the website
with open('website4.html') as fid:
    website = fid.read()

print 'Serving HTTP on port %s ...' % PORT
while True:  # forever
    try:
        print "waiting for a client"

        # Accept an incoming connection:
        client_connection, client_address = listen_socket.accept()

        # Allow the client 0.5 seconds to send the request
        ready = select.select([client_connection], [], [], 0.5)

        # If the client sent a request
        if ready[0]:
            # Receive the request
            request = client_connection.recv(1024)
            print request

            # check if client is asking for the website
            if len(request)>14:
                if request[:14] == 'GET / HTTP/1.1':
                    # create the response
                    with open('website4.html') as fid:
                        website = fid.read()
                    http_response = """\
HTTP/1.1 200 OK

""" + website
                    print "sending my response"
                    # send the response
                    client_connection.sendall(http_response)
                    print "closing connection"
        # close the connection
        client_connection.close()
        print "done"
    except socket.error as e:
        print e
