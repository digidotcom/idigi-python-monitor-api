# -*- coding: utf-8 -*
# Copyright (c) 2012 Digi International Inc., All Rights Reserved
# 
# This software contains proprietary and confidential information of Digi
# International Inc.  By accepting transfer of this copy, Recipient agrees
# to retain this software in confidence, to prevent disclosure to others,
# and to make no use of this software other than that for which it was
# delivered.  This is an published copyrighted work of Digi International
# Inc.  Except as permitted by federal law, 17 USC 117, copying is strictly
# prohibited.
# 
# Restricted Rights Legend
#
# Use, duplication, or disclosure by the Government is subject to
# restrictions set forth in sub-paragraph (c)(1)(ii) of The Rights in
# Technical Data and Computer Software clause at DFARS 252.227-7031 or
# subparagraphs (c)(1) and (2) of the Commercial Computer Software -
# Restricted Rights at 48 CFR 52.227-19, as applicable.
#
# Digi International Inc. 11001 Bren Road East, Minnetonka, MN 55343
"""
A Push Monitoring Client for subscribing to events that occur in 
iDigi.
"""
import httplib
import json
import logging
import socket, ssl, struct, time
import select
import urllib
import zlib

from base64 import encodestring
from xml.dom.minidom import getDOMImplementation, parseString
from Queue import Queue, Empty
from threading import Thread

LOG = logging.getLogger("push_client")

# Dom Implementation to work with
DOM = getDOMImplementation()

# Push Opcodes.
CONNECTION_REQUEST = 0x01
CONNECTION_RESPONSE = 0x02
PUBLISH_MESSAGE = 0x03
PUBLISH_MESSAGE_RECEIVED = 0x04

# Possible Responses from iDigi with respect to Push.
STATUS_OK = 200
STATUS_UNAUTHORIZED = 403
STATUS_BAD_REQUEST = 400

# Ports to Connect on for Push.
PUSH_OPEN_PORT = 3200
PUSH_SECURE_PORT = 3201

def _read_msg_header(sck):
    """
    Perform a read on input socket to consume headers and then return 
    a tuple of message type, message length.

    :param: sck: Socket to read from.
    """
    data = ""
    while len(data) < 6 :
        try:
            new_data = sck.recv(6 - len(data))
            if len(new_data) == 0:
                break
            data += new_data
        except ssl.SSLError:
            # This can happen when select gets triggered 
            # for an SSL socket and data has not yet been 
            # read.
            time.sleep(.01)
        except Exception:
            break
    
    if len(data) < 6:
        return (None, None)

    response_type = struct.unpack('!H', data[0:2])[0]
    message_length = struct.unpack('!i', data[2:6])[0]

    return (response_type, message_length)

def _read_msg(sck, message_length):
    """
    Perform a read on input socket to consume message and then return the
    payload and block_id in a tuple.

    :param: sck: Socket to read from.
    :param: message_length: Expected length of the message.
    """
    data = ""
    while len(data) < message_length:
        try:
            new_data = sck.recv(message_length - len(data))
            if len(new_data) == 0:
                break
            data = data + new_data  
        except ssl.SSLError:
            # This can happen when select gets triggered 
            # for an SSL socket and data has not yet been 
            # read.
            time.sleep(.01)
        except Exception:
            break

    if len(data) < message_length:
        return None

    block_id = struct.unpack('!H', data[0:2])[0]
    compression = struct.unpack('!B', data[4:5])[0]
    payload = data[10:]

    if compression == 0x01:
        # Data is compressed, uncompress it.
        # Note, this doesn't work yet.
        payload = zlib.decompress(payload)

    return (payload, block_id)

class PushException(Exception):
    """
    Indicates an issue interacting with iDigi Push Functionality.
    """
    pass

class PushSession(object):
    """
    A PushSession is responsible for establishing a socket connection
    with iDigi to receive events generated by Devices connected to 
    iDigi.
    """
    
    def __init__(self, callback, monitor_id, client):
        """
        Creates a PushSession for use with interacting with iDigi's
        Push Functionality.
        
        Arguments:
        callback   -- The callback function to invoke when data is received.  
                      Must have 1 required parameter that will contain the
                      payload.
        monitor_id -- The id of the Monitor to observe.
        client     -- The client object this session is derived from.
        """
        self.callback   = callback
        self.monitor_id = monitor_id
        self.client     = client
        self.socket     = None
        self.log        = logging.getLogger("push_session[%s]" % monitor_id)
        
    def send_connection_request(self):
        """
        Sends a ConnectionRequest to the iDigi server using the credentials
        established with the id of the monitor as defined in the monitor 
        member.
        """
        try:
            self.log.info("Sending ConnectionRequest for Monitor %s." 
                % self.monitor_id)
            # Send connection request and perform a receive to ensure
            # request is authenticated.
            # Protocol Version = 1.
            payload  = struct.pack('!H', 0x01)
            # Username Length.
            payload += struct.pack('!H', len(self.client.username))
            # Username.
            payload += self.client.username
            # Password Length.
            payload += struct.pack('!H', len(self.client.password))
            # Password.
            payload += self.client.password
            # Monitor ID.
            payload += struct.pack('!L', int(self.monitor_id))

            # Header 6 Bytes : Type [2 bytes] & Length [4 Bytes]
            # ConnectionRequest is Type 0x01.
            data = struct.pack("!HL", CONNECTION_REQUEST, len(payload))

            # The full payload.
            data += payload

            # Send Connection Request.
            self.socket.send(data)

            # Set a 10 second blocking on recv, if we don't get any data
            # within 10 seconds, timeout which will throw an exception.
            self.socket.settimeout(10)

            # Should receive 10 bytes with ConnectionResponse.
            response = self.socket.recv(10)

            # Make socket blocking.
            self.socket.settimeout(0)

            if len(response) != 10:
                raise PushException("Length of Connection Request Response \
(%d) is not 10." % len(response))

            # Type
            response_type = int(struct.unpack("!H", response[0:2])[0])
            if response_type != CONNECTION_RESPONSE:
                raise PushException("Connection Response Type (%d) is not \
ConnectionResponse Type (%d)." % (response_type, CONNECTION_RESPONSE))

            status_code = struct.unpack("!H", response[6:8])[0]
            self.log.info("Got ConnectionResponse for Monitor %s. Status %s." 
                % (self.monitor_id, status_code))
            if status_code != STATUS_OK:
                raise PushException("Connection Response Status Code (%d) is \
not STATUS_OK (%d)." % (status_code, STATUS_OK))

            # Add Incredibly arbitrary sleep as it takes ms for iDigi to 
            # inform every member of Cluster that there is a new monitor
            # session.
            time.sleep(.5)
        except Exception, exception:
            self.socket.close()
            self.socket = None
            raise exception

    def start(self):
        """
        Creates a TCP connection to the iDigi Server and sends a 
        ConnectionRequest message.
        """
        self.log.info("Starting Insecure Session for Monitor %s." 
            % self.monitor_id)
        if self.socket is not None:
            raise Exception("Socket already established for %s." % self)
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.client.hostname, PUSH_OPEN_PORT))
            self.socket.setblocking(0)
        except Exception, exception:
            self.socket.close()
            self.socket = None
            raise exception
        
        self.send_connection_request()
            
    def stop(self):
        """
        Closes the socket associated with this session and puts Session 
        into a state such that it can be re-established later.
        """
        if self.socket is not None:
            self.socket.close()
            self.socket = None

class SecurePushSession(PushSession):
    """
    SecurePushSession extends PushSession by wrapping the socket connection
    in SSL.  It expects the certificate to match any of those in the passed
    in ca_certs member file.
    """
    
    def __init__(self, callback, monitor_id, client, ca_certs=None):
        """
        Creates a PushSession wrapped in SSL for use with interacting with 
        iDigi's Push Functionality.
        
        Arguments:
        callback   -- The callback function to invoke when data is received.  
                      Must have 1 required parameter that will contain the
                      payload.
        monitor_id -- The id of the Monitor to observe.
        client     -- The client object this session is derived from.
        
        Keyword Arguments:
        ca_certs -- Path to a file containing Certificates.  If not None,
                    iDigi Server must present a certificate present in the 
                    ca_certs file.
        """
        PushSession.__init__(self, callback, monitor_id, client)
        self.ca_certs = ca_certs
    
    def start(self):
        """
        Creates a SSL connection to the iDigi Server and sends a 
        ConnectionRequest message.
        """
        self.log.info("Starting SSL Session for Monitor %s." % self.monitor_id)
        if self.socket is not None:
            raise Exception("Socket already established for %s." % self)
        
        try:
            # Create socket, wrap in SSL and connect.
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Validate that certificate server uses matches what we expect.
            if self.ca_certs is not None:
                self.socket = ssl.wrap_socket(self.socket, 
                                                cert_reqs=ssl.CERT_REQUIRED, 
                                                ca_certs=self.ca_certs)
            else:
                self.socket = ssl.wrap_socket(self.socket)

            self.socket.connect((self.client.hostname, PUSH_SECURE_PORT))
            self.socket.setblocking(0)
        except Exception, exception:
            self.socket.close()
            self.socket = None
            raise exception
            
        self.send_connection_request()

class CallbackWorkerPool(object):
    """
    A Worker Pool implementation that creates a number of predefined threads
    used for invoking Session callbacks.
    """

    def __consume_queue(self):
        """
        Continually blocks until data is on the internal queue, then calls 
        the session's registered callback and sends a PublishMessageReceived 
        if callback returned True.
        """
        while True:
            session, block_id, data = self.__queue.get()
            try:
                if session.callback(data):
                    # Send a Successful PublishMessageReceived with the 
                    # block id sent in request
                    if self.__write_queue is not None:
                        response_message = struct.pack('!HHH', 
                                            PUBLISH_MESSAGE_RECEIVED, 
                                            block_id, 200)
                        self.__write_queue.put((session.socket, 
                            response_message))
            except Exception, exception:
                self.log.exception(exception)

            self.__queue.task_done()


    def __init__(self, write_queue=None, size=20):
        """
        Creates a Callback Worker Pool for use in invoking Session Callbacks 
        when data is received by a push client.

        :param write_queue: Queue used for queueing up socket write events 
        for when a payload message is received and processed.
        :param size: The number of worker threads to invoke callbacks.
        """
        # Used to queue up PublishMessageReceived events to be sent back to 
        # the iDigi server.
        self.__write_queue = write_queue
        # Used to queue up sessions and data to callback with.
        self.__queue = Queue(size)
        # Number of workers to create.
        self.size = size
        self.log  = logging.getLogger('callback_worker_pool')

        for _ in range(size): 
            worker = Thread(target=self.__consume_queue)
            worker.daemon = True
            worker.start()

    def queue_callback(self, session, block_id, data):
        """
        Queues up a callback event to occur for a session with the given 
        payload data.  Will block if the queue is full.

        :param session: the session with a defined callback function to call.
        :param block_id: the block_id of the message received.
        :param data: the data payload of the message received.
        """
        self.__queue.put((session, block_id, data))        

def push_client(username, password, **kwargs):
    """
    Returns a :class:`PushClient` for context-management.

    :param username: Username to authenticate with.
    :param password: Password to authenticate with.
    """
    return PushClient(username, password, **kwargs)

class PushClient(object):
    """
    A Client for the 'Push' feature in iDigi.
    """
    
    def __init__(self, username, password, hostname='developer.idigi.com', 
                secure=True, ca_certs=None, workers=1):
        """
        Creates a Push Client for use in creating monitors and creating sessions 
        for them.
        
        :param username: Username of user in iDigi to authenticate with.
        :param password: Password of user in iDigi to authenticate with.:
        :param hostname: Hostname of iDigi server to connect to.
        :param secure: Whether or not to create a secure SSL wrapped session.
        :param ca_certs: Path to a file containing Certificates.  If not None, 
        iDigi Server must present a certificate present in the ca_certs file 
        if 'secure' is specified to True.
        """
        self.hostname     = hostname
        self.username     = username
        self.password     = password
        self.secure       = secure
        self.ca_certs     = ca_certs
        
        # A dict mapping Sockets to their PushSessions
        self.sessions          = {}
        # IO thread is used monitor sockets and consume data.
        self.__io_thread       = None
        # Writer thread is used to send data on sockets.
        self.__writer_thread   = None
        # Write queue is used to queue up data to write to sockets.
        self.__write_queue     = Queue()
        # A pool that monitors callback events and invokes them.
        self.__callback_pool   = CallbackWorkerPool(self.__write_queue, 
                                                    size=workers)

        self.closed            = False
        self.log               = logging.getLogger('push_client')

        self.headers           = {
            'Authorization': 'Basic ' \
            + encodestring('%s:%s' % (self.username,self.password))[:-1]
        }

    def get_http_connection(self):
        """
        Returns a HTTPConnection or HTTPSConnection (depending on whether or 
        not secure is set) to be used for interfacing with iDigi web services.
        """
        return httplib.HTTPSConnection(self.hostname) if self.secure \
            else httplib.HTTPConnection(self.hostname)


    def create_monitor(self, topics, batch_size=1, batch_duration=0, 
        compression='gzip', format_type='xml'):
        """
        Creates a Monitor instance in iDigi for a given list of topics.
        
        Arguments:
        topics -- a string list of topics (i.e. ['DeviceCore[U]', 
                  'FileDataCore']).
        
        Keyword Arguments:
        batch_size     -- How many Msgs received before sending data.
        batch_duration -- How long to wait before sending batch if it does not 
                          exceed batch_size.
        compression    -- Compression value (i.e. 'gzip').
        format_type    -- What format server should send data in (i.e. 'xml' or 
                          'json').
        
        Returns a string of the created Monitor Id (i.e. 9001)
        """
        # Create Monitor Request XML.
        monitor_req = DOM.createDocument(None, "Monitor", None)
        root = monitor_req.documentElement

        attrs = { 'monTopic' : ','.join(topics), 
                    'monBatchSize' : str(batch_size),
                    'monBatchDuration' : str(batch_duration),
                    'monFormatType' : format_type,
                    'monTransportType' : 'tcp',
                    'monCompression' : compression }

        for element, value in attrs.items():
            el = monitor_req.createElement(element)
            el.appendChild(monitor_req.createTextNode(value))
            root.appendChild(el)

        request = root.toxml()

        # POST Monitor Request.
        connection = self.get_http_connection()
        connection.request('POST', '/ws/Monitor', request, 
                                        self.headers)
        response = connection.getresponse()
        try:
            if response.status == 201:
                location = response.getheader('location').split('/')[-1]
                return location
            else:
                raise Exception("Monitor Could not be Created (%d): %s" \
                    % (response.status, response.read()))
        finally:
            connection.close()


    def delete_monitor(self, monitor_id):
        """
        Attempts to Delete a Monitor from iDigi.  Throws exception if 
        Monitor does not exist.
        
        Arguments:
        monitor_id -- id of the Monitor (i.e. 1000).
        """

        connection = self.get_http_connection()
        connection.request('DELETE', '/ws/Monitor/%s' % monitor_id, 
                            headers=self.headers)
        response = connection.getresponse()

        try:
            if response.status != 200:
                raise Exception("Monitor Could not be Deleted (%s): %s" \
                    % (response.status, response.read()))
        finally:
            connection.close()
        
    def get_monitor(self, topics):
        """
        Attempts to find a Monitor in iDigi that matches the input list of 
        topics.
        
        Arguments:
        topics -- a string list of topics 
                  (i.e. ['DeviceCore[U]', 'FileDataCore']).
        
        Returns a monitor ID if found, otherwise None.
        """
        # Query for Monitor conditionally by monTopic.
        params = {'condition' : "monTopic='%s'" % ','.join(topics)}
        url = '/ws/Monitor/.json?' + urllib.urlencode([(key,params[key]) \
            for key in params])
        
        connection = self.get_http_connection()
        connection.request('GET', url, headers=self.headers)

        response = connection.getresponse()

        try:
            content = response.read()

            if response.status != 200:
                raise Exception("Monitor Could not be Retrieved (%s): %s" \
                    % (response.status, content))

            monitor_data = json.loads(content)

            # If no matching Monitor found, return None.
            if monitor_data['resultSize'] == '0': return None
            # Otherwise grab the first found monitor's id.
            return monitor_data['items'][0]['monId']
        finally:
            connection.close()
        
    def __restart_session(self, session):
        """
        Restarts and re-establishes session.

        Arguments:
        session -- The session to restart.
        """
        # remove old session key, if socket is None, that means the
        # session was closed by user and there is no need to restart.
        if session.socket is not None:
            self.log.info("Attempting restart session for Monitor Id %s."
             % session.monitor_id)
            del self.sessions[session.socket.fileno()]
            session.stop()
            session.start()
            self.sessions[session.socket.fileno()] = session

    def __writer(self):
        """
        Indefinitely checks the writer queue for data to write
        to socket.
        """
        while not self.closed:
            try:
                sock, data = self.__write_queue.get(timeout=0.1)
                sock.send(data)
                self.__write_queue.task_done()
            except Empty:
                pass # nothing to write after timeout

    def __select(self):
        """
        While the client is not marked as closed, performs a socket select
        on all PushSession sockets.  If any data is received, parses and
        forwards it on to the callback function.  If the callback is 
        successful, a PublishMessageReceived message is sent.
        """
        try:
            while not self.closed:
                try:
                    inputready = \
                        select.select(self.sessions.keys(), [], [], 0.1)[0]

                    for sock in inputready:
                        session = self.sessions[sock]
                        sck = session.socket
                        
                        # Read header information before receiving rest of
                        # message.
                        (response_type, message_length) = _read_msg_header(sck)

                        if response_type is None:
                            # Data could not be read, assume socket closed.
                            if session.socket is not None:
                                self.log.error("Socket closed for " \
                                    "Monitor %s." % session.monitor_id)
                                self.__restart_session(session) 
                            continue
                        
                        if response_type != PUBLISH_MESSAGE:
                            self.log.warn("Response Type (%x) does not match " \
                                "PublishMessageReceived (%x)" \
                                % (response_type, PUBLISH_MESSAGE))
                            continue

                        (payload, block_id) = _read_msg(sck, message_length)
                        
                        # If payload is None, message was malformed or socket 
                        # was closed, in this case, skip queuing and assume 
                        # socket was closed.
                        if payload is not None:
                            # Enqueue payload into a callback queue to be
                            # invoked.
                            self.__callback_pool.queue_callback(session, 
                                block_id, payload)
                        else:
                            # If payload is less than the message length, 
                            # assume socket closed.
                            if session.socket is not None:
                                self.log.error("Socket closed for " \
                                    "Monitor %s." % session.monitor_id)
                                self.__restart_session(session)
                except Exception:
                    # Evaluate sessions, if socket is gone delete the session.
                    for sck in self.sessions.keys():
                        session = self.sessions[sck]
                        if session.socket is None:
                            del self.sessions[sck]

        finally:
            for session in self.sessions.values():
                if session is not None: 
                    session.stop()
    
    def __init_threads(self):
        """
        Initializes the IO and Writer threads
        """
        if self.__io_thread is None:
            self.__io_thread = Thread(target=self.__select)
            self.__io_thread.start()

        if self.__writer_thread is None:
            self.__writer_thread = Thread(target=self.__writer)
            self.__writer_thread.start()

           
    def create_session(self, callback, monitor_id):
        """
        Creates and Returns a PushSession instance based on the input monitor
        and callback.  When data is received, callback will be invoked.
        If neither monitor or monitor_id are specified, throws an Exception.
        
        Arguments:
        callback -- Callback function to call when PublishMessage messages are
                    received. Expects 1 argument which will contain the 
                    payload of the pushed message.  Additionally, expects 
                    function to return True if callback was able to process 
                    the message, False or None otherwise.
        monitor_id -- The id of the Monitor, will be queried 
                      to understand parameters of the monitor.
        """
        self.log.info("Creating Session for Monitor %s." % monitor_id)
        session = SecurePushSession(callback, monitor_id, self, self.ca_certs) \
            if self.secure else PushSession(callback, monitor_id, self)

        session.start()
        self.sessions[session.socket.fileno()] = session
        
        self.__init_threads()
        return session
    
    def stop_all(self):
        """
        Stops all session activity.  Blocks until io and writer thread dies.
        """
        if self.__io_thread is not None:
            self.log.info("Waiting for I/O thread to stop...")
            self.closed = True
            
            while self.__io_thread.is_alive():
                time.sleep(1)

        if self.__writer_thread is not None:
            self.log.info("Waiting for Writer Thread to stop...")
            self.closed = True

            while self.__writer_thread.is_alive():
                time.sleep(1)

        self.log.info("All worker threads stopped.")

def json_cb(data):
    """
    Sample callback, parses data as json and pretty prints it.
    Returns True if json is valid, False otherwise.
    
    Arguments:
    data -- The payload of the PublishMessage.
    """
    try:
        json_data = json.loads(data)
        LOG.info("Data Received %s" % json.dumps(json_data, sort_keys=True, 
                    indent=4))
        return True
    except Exception, exception:
        print exception

    return False

def xml_cb(data):
    """
    Sample callback, parses data as xml and pretty prints it.
    Returns True if xml is valid, False otherwise.

    Arguments:
    data -- The payload of the PublishMessage.
    """
    try:
        dom = parseString(data)
        print "Data Received: %s" % (dom.toprettyxml())

        return True
    except Exception, exception:
        print exception
    
    return False

def get_parser():
    """ Parser for this script """
    import argparse
    parser = argparse.ArgumentParser(description="iDigi Push Client Sample", 
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('username', type=str,
        help='Username to authenticate with.')

    parser.add_argument('password', type=str,
        help='Password to authenticate with.')

    parser.add_argument('--topics', '-t', dest='topics', action='store', 
        type=str, default='DeviceCore', 
        help='A comma-separated list of topics to listen on.')

    parser.add_argument('--host', '-a', dest='host', action='store', 
        type=str, default='developer.idigi.com', 
        help='iDigi server to connect to.')

    parser.add_argument('--ca_certs', dest='ca_certs', action='store',
        type=str,
        help='File containing iDigi certificates to authenticate server with.')

    parser.add_argument('--insecure', dest='secure', action='store_false',
        default=True,
        help='Prevent client from making secure (SSL) connection.')

    parser.add_argument('--compression', dest='compression', action='store',
        type=str, default='gzip', choices=['none', 'gzip'],
        help='Compression type to use.')

    parser.add_argument('--format', dest='format', action='store',
        type=str, default='json', choices=['json', 'xml'],
        help='Format data should be pushed up in.')

    parser.add_argument('--batchsize', dest='batchsize', action='store',
        type=int, default=1,
        help='Amount of messages to batch up before sending data.')

    parser.add_argument('--batchduration', dest='batchduration', action='store',
        type=int, default=60,
        help='Seconds to wait before sending batch if batchsize not met.')
    
    return parser

def main():
    """ Main function call """
    args = get_parser().parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', 
                datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
    LOG.info("Creating Push Client.")
    client = push_client(args.username, args.password, hostname=args.host,
                        secure=args.secure, ca_certs=args.ca_certs)

    topics = args.topics.split(',')

    LOG.info("Checking to see if Monitor Already Exists.")
    monitor_id = client.get_monitor(topics)

    # Delete Monitor if it Exists.
    if monitor_id is not None:
        LOG.info("Monitor already exists, deleting it.")
        client.delete_monitor(monitor_id)

    monitor_id = client.create_monitor(topics, format_type=args.format,
        compression=args.compression, batch_size=args.batchsize, 
        batch_duration=args.batchduration)

    try:
        callback = json_cb if args.format == "json" else xml_cb
        client.create_session(callback, monitor_id)
        while True:
            time.sleep(3.14)
    except KeyboardInterrupt:
        # Expect KeyboardInterrupt (CTRL+C or CTRL+D) and print friendly msg.
        LOG.warn("Closing Sessions and Cleaning Up.")
    finally:
        client.stop_all()
        LOG.info("Deleting Monitor %s." % monitor_id)
        client.delete_monitor(monitor_id)
        LOG.info("Done")

if __name__ == "__main__":
    main()
