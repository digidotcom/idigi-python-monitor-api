import sys
sys.path.append('..')

import push_client
import logging
import time
import json
import base64


def trace_callback(data):
    try:
        json_data = json.loads(data)
        file_data = base64.decodestring(json_data['Document']['Msg']['FileData']['fdData'])
        sys.stdout.write(file_data)
        return True
    except Exception, e:
        print e
    return False

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', 
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)

log = logging.getLogger(__name__)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="iDigi Device Tracing Sample", 
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('username', type=str,
        help='Username to authenticate with.')

    parser.add_argument('password', type=str,
        help='Password to authenticate with.')

    parser.add_argument('device_id', type=str,  
        help='The full device id of the device to capture tracing on.')

    parser.add_argument('--host', '-a', dest='host', action='store', 
        type=str, default='test.idigi.com', 
        help='iDigi server to connect to.')
    
    args = parser.parse_args()

    client = push_client.PushClient(args.username, args.password, 
                        hostname=args.host,
                        secure=False, ca_certs='../idigi.pem')

    topics = ['FileData/~%%2F%s/trace.log' % args.device_id ]

    log.info("Checking to see if Monitor Already Exists.")
    monitor = client.get_monitor(topics)

    # Delete Monitor if it Exists.
    if monitor is not None:
        log.info("Monitor already exists, deleting it.")
        client.delete_monitor(monitor)

    monitor = client.create_monitor(topics, format_type='json')

    try:
        callback = trace_callback
        session = client.create_session(callback, monitor)
        while True:
            time.sleep(3.14)
    except KeyboardInterrupt:
        # Expect KeyboardInterrupt (CTRL+C or CTRL+D) and print friendly msg.
        log.warn("Keyboard Interrupt Received.  \
    Closing Sessions and Cleaning Up.")
    finally:
        client.stop_all()
        #client.delete_monitor(monitor)
