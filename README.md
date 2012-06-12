iDigi Push Monitor API for Python
=================================

iDigi's Push Monitoring service allows TCP clients to receive asynchronous notification of various events as they occur in iDigi.  This project is an easy to use reference Python implementation of an iDigi Push Monitoring API.

The general usage pattern of the Monitoring Service is:

1. Create a Monitor for Resources (i.e. Device data) you want to observe by POSTing to `/ws/Monitor`.
2. Create a TCP socket and send a `ConnectionRequest` message on the socket which includes the id of the created Monitor and user credentials.
3. Server sends resource events over the established TCP client to the socket as they occur.

More information about the iDigi monitor service may be found in the [iDigi Web Services Programming Guide](http://ftp1.digi.com/support/documentation/90002008_E.pdf).

Prerequisites
-------------
Python 2.6+ is required to utilize this library.  The argparse library is 
required to execute the example cli program.  Argparse comes with Python 2.7 
but may be installed using pip:

    sudo pip install argparse

Installation
------------
This library can be installed as a python module by executing:

    sudo python setup.py install

Example Usage
-------------
The Push Monitoring API is very easy to use.  Following the usage pattern detailed above a Push Monitor can be created and used in the following manner.

First, import the api and create a push client object with your iDigi login credentials.

```python
from idigi_monitor_api import push_client

client = push_client("username", "password")
```

Next, create a Push Monitor (this will POST to /ws/Monitor).

```python
monitor_id = client.create_monitor(['DeviceCore','FileData'])
```

Before creating your connection, you will need to define a Callback Function which will be invoked whenever an event occurs in the iDigi Platform.  Here's a simple callback function that parses data passed in as json and pretty prints it.

```python
import json

def json_cb(data):
    json_data = json.loads(data)
    print "Data Received %s" % json.dumps(json_data, sort_keys=True, indent=4)
```

Finally, create a Push Session providing the id of the Monitor created previously and the callback function defined.  Note that this does not block, so you may want to add a loop to prevent your program from exiting.

```python
import time

try:
    client.create_session(json_cb, monitor_id)
    while True:
        time.sleep(.31416)
except KeyboardInterrupt:
    # Expect KeyboardInterrupt (CTRL+C or CTRL+D) and print friendly msg.
    print "Closing Sessions and Cleaning Up."
finally:
    # Stop Push Client's Sessions and Delete Monitor.
    client.stop_all()
    client.delete_monitor(monitor_id)
    print "Done"
```

And that's it!  You can verify your code by disconnecting a device from iDigi:

```json
Data Received {
    "Document": {
        "Msg": {
            "DeviceCore": {
                "devConnectwareId": "00000000-00000000-00409DFF-FF49B68F", 
                "dpConnectionStatus": 0, 
                ...
            }, 
            "group": "*", 
            "operation": "UPDATE", 
            "timestamp": "2012-06-12T03:18:45.381Z", 
            "topic": "1210/DeviceCore/7201/0"
        }
    }
}
```

**Note**: It may be of benefit to enable logging to understand what the API is doing, a simple way to do so:

```python
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', 
                datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
```

Example CLI Program
-------------------
An example CLI program, `push_client.py`, is provided in the `examples` directory.  It demonstrates the utility of the API by creating a Push Monitor, establishing a socket, and printing data as it's received.

```
usage: push_client.py [-h] [--topics TOPICS] [--host HOST] [--insecure]
                      [--compression {none,gzip}] [--format {json,xml}]
                      [--batchsize BATCHSIZE] [--batchduration BATCHDURATION]
                      username password

iDigi Push Client Sample

positional arguments:
  username              Username to authenticate with.
  password              Password to authenticate with.

optional arguments:
  -h, --help            show this help message and exit
  --topics TOPICS, -t TOPICS
                        A comma-separated list of topics to listen on.
                        (default: DeviceCore)
  --host HOST, -a HOST  iDigi server to connect to. (default: my.idigi.com)
  --insecure            Prevent client from making secure (SSL) connection.
                        (default: False)
  --compression {none,gzip}, -c {none,gzip}
                        Compression type to use. (default: gzip)
  --format {json,xml}, -f {json,xml}
                        Format data should be pushed up in. (default: json)
  --batchsize BATCHSIZE, -b BATCHSIZE
                        Amount of messages to batch up before sending data.
                        (default: 1)
  --batchduration BATCHDURATION, -d BATCHDURATION
                        Seconds to wait before sending batch if batchsize not
                        met. (default: 60)
```

License
-------
This source code is issues under the [Mozilla Public License v2.0](http://mozilla.org/MPL/2.0/).  More information can be found in the LICENSE file.

Issues
------
Please feel free to open an Issue or create a Pull Request if you encounter any problems or have any suggestions for improving this project.
