#!/usr/bin/python
import sys
sys.path.append('..')

from idigi_monitor_api import push_client
import logging
import time
import json
import base64


def trace_callback(data):
    try:
        json_data = json.loads(data)
        timestamp = str(json_data['Document']['Msg']['timestamp'])
        operation = str(json_data['Document']['Msg']['operation'])
        device_id = str(json_data['Document']['Msg']['DiaChannelDataFull']['id']['devConnectwareId'])
        channel = str((json_data['Document']['Msg']['DiaChannelDataFull']['id']['ddInstanceName'] +
                   "." +
                   json_data['Document']['Msg']['DiaChannelDataFull']['id']['dcChannelName']))
        string_val = str(json_data['Document']['Msg']['DiaChannelDataFull']['dcdStringValue'])
	sys.stdout.write("%s %s %s %s %s\n" % 
                          (timestamp, operation, device_id, channel, string_val))
        return True
    except Exception, e:
        print repr(e)
    return False

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', 
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)

log = logging.getLogger(__name__)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="iDigi Dia Event Sample", 
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('username', type=str,
        help='Username to authenticate with.')

    parser.add_argument('password', type=str,
        help='Password to authenticate with.')

    parser.add_argument('--host', '-a', dest='host', action='store', 
        type=str, default='developer.idigi.com', 
        help='iDigi server to connect to.')
    
    args = parser.parse_args()

    client = push_client(args.username, args.password, 
                        hostname=args.host,
                        secure=True)

    topics = ['DiaChannelDataFull']

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
