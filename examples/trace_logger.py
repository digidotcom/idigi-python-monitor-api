import digicli
import math
import select
import socket
import time
import idigidata

import StringIO

def flush_trace_cache(cache):

    try:
        try:
            cache_value = cache.getvalue()
            if len(cache_value) > 0:
                (success, error, errormsg) =\
                    idigidata.send_to_idigi(cache_value, 
                                            "trace.log", append=False)
                if not success:
                    print "Failed to Send over Data Service, error %d, message: %s" % (error, errormsg)

        except Exception, e:
            print "trace writer failed with exception: ", e
    finally:
        try:
            cache.truncate(0)
        except Exception, e:
            print "truncate failed with exception: " , e

def syslog_server():
    trace_cache = StringIO.StringIO()
    last_write = time.clock()
    trace_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        try:
            # Bind to syslog port, 514
            trace_socket.bind(("", 514))

            print "Entering Trace Read Now..."

            while(True):
                rlist, wlist, xlist = select.select([trace_socket], [], [], 5)

                if trace_socket in rlist:
                    payload, src = trace_socket.recvfrom(1024)

                    trace_cache.write(payload)
                
                if(math.fabs(time.clock() - last_write)) > 10:
                    flush_trace_cache(trace_cache)
                    last_write = time.clock()
        except Exception, e:
            print "Exception during trace read: ", e
    finally:
        trace_socket.close()
        print "Trace thread ending"
    
if __name__ == "__main__":
    try:
        (status, result) = digicli.digicli("set trace state=on syslog=on mask=sms:*,idigi:*,edp:*,printf:-* loghost=127.0.0.1")
        if not status:
            print "Initial CLI trace set failed"
        else:
            syslog_server()
    except Exception, e:
        print "Initial CLI trace set failed with exception: %s" % e