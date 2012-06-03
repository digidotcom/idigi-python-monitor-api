import argparse
import json
import logging
import time

from xml.dom.minidom import parseString
from idigi_monitor_api import push_client

LOG = logging.getLogger("push_client")

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

    parser.add_argument('--insecure', dest='insecure', action='store_true',
        default=False,
        help='Prevent client from making secure (SSL) connection.')

    parser.add_argument('--compression', '-c',  dest='compression', 
        action='store', type=str, default='gzip', choices=['none', 'gzip'],
        help='Compression type to use.')

    parser.add_argument('--format', '-f', dest='format', action='store',
        type=str, default='json', choices=['json', 'xml'],
        help='Format data should be pushed up in.')

    parser.add_argument('--batchsize', '-b', dest='batchsize', action='store',
        type=int, default=1,
        help='Amount of messages to batch up before sending data.')

    parser.add_argument('--batchduration', '-d', dest='batchduration', 
        action='store', type=int, default=60,
        help='Seconds to wait before sending batch if batchsize not met.')
    
    return parser

def main():
    """ Main function call """
    args = get_parser().parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', 
                datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
    LOG.info("Creating Push Client.")

    client = push_client(args.username, args.password, hostname=args.host,
                        secure=not args.insecure)

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
            time.sleep(.31416)
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