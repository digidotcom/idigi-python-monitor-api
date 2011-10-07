# Copyright (c) 2011 Digi International Inc., All Rights Reserved
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
idigi_ws_api is a Convenience API for utilizing the RESTful iDigi Web Service
APIs to access and manipulate Resources on the iDigi Server, of which includes
Devices, Customers, and Device Data (Storage, Dia, Xbee).

Example usage:

Creating an API object:

     import idigi_ws_api
     api = idigi_ws_api.Api('username', 'password')

Provisioning a Device against customer account by Device ID and working with it:

     # Create DeviceCore resource
     device = idigi_ws_api.RestResource.create('DeviceCore',
                  devConnectwareId='00000000-00000000-00409DFF-FF0000001')

     location = api.post(device)

     print location
     >> DeviceCore/6576/0

     # Retrieve Device, maps XML response to a custom python object extending
     # RestResource, maps child elements as object attrs.
     device = api.get_first(location)
    
     print device.devRecordStartDate
     >> 2011-01-23T22:37:00Z

     print device
     >> {'dpFirmwareLevel': '0', 'devConnectwareId':
     >> '00000000-00000000-00409DFF-FF000001', 'devTerminated': 'false',
     >> 'devEffectiveStartDate': '2011-01-23T22:37:00Z',
     >> 'dpConnectionStatus': '1', 'grpId': '1', 'cstId': '1',
     >> 'dpDeviceType': 'ConnectPort X2', 'dpRestrictedStatus': '0',
     >> 'devRecordStartDate': '2011-01-23T22:37:00Z',
     >> 'id': <idigi_ws_api.id object at 0x00000000029123C8>}

     print device.id
     >> {'devVersion': '1', 'devId': '6576'}

     print device.id.devVersion
     >> 1

Retrieving Metering Consumption Values from all Metering Server Clusters against
account.

    # Retrieve all 0x0 attributes on the 0x702 (1794) server (0x0) Cluster.
    attributes = api.get('XbeeAttributeDataCore',
                             condition=\"xcClusterId='1794' \
                             and xcClusterType='0' and xaAttributeId='0'\")

    # Map Xbee Address/Endpoint ID to consumption
    consumption_vals = dict([(\"%s/%s\" % (a.id.xpExtAddr, a.id.xeEndpointId),
                              a.xadAttributeIntegerValue) for a in attributes])

    print consumption_vals
    >> { '00:00:06:12:34:5B:00:02/20': '2369',
    >>   'A0:00:01:12:34:04:00:02/18': '7324',
    >>   '00:00:65:10:00:01:00:01/14': '120023'}

Turn on Attribute Reporting on a Metering CSD Attribute

   # Create id identifying the attribute to enable reporting for
   id = idigi_ws_api.RestResource.create('id', xaAttributeId='0', \
            xcClusterId='1794', xcClusterType='0', xeEndpointId='9', \
            xpExtAddr=''00:40:9D:12:34:58:00:02')

   # Create an XbeeAttributeReportingCore object that enables reporting
   # on a 5 minute to 15 minute interval with a reportable change of 50
   report = idigi_ws_api.RestResource.create('XbeeAttributeReportingCore', \
                xarMinReportingInterval='600', xarMaxReportingInterval='1800', \
                xarTimeout='60', xarEnabled='true', xarReportableChange='50', \
                devConnectwareId='00000000-00000000-00409DFF-FF123458', id=id)

   location = api.put(report)

   print location
   >> XbeeAttributeReportingCore/00:40:9D;12;34;58:00:02/9/0/1794/0

   # Delete Report
   api.delete(location)
   
Posting an SCI Request to a Device:

        # SCI request to send the redirect, redirect device to same server.
        redirect_request = \"""
            <sci_request version="1.0">
                <redirect>
                    <targets>
                        <device id="%s"/>
                    </targets>
                    <destinations>
                        <destination>%s</destination>
                    </destinations>
                </redirect>
            </sci_request>\""" % (device_id, api.hostname)

        api.sci(redirect_request)

"""

import logging
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', 
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
log = logging.getLogger(__name__)

import httplib, urllib
from base64 import encodestring
from xml.dom.minidom import getDOMImplementation, parseString, Element
import uuid, re

import warnings

impl = getDOMImplementation()

def enum(**enums):
    return type('Enum', (), enums)
    
Roles = enum(SYSTEM_ADMIN=['6', '2', '5'], READ_ONLY_SYS_ADMIN=['3','10','6'],
                SYSTEM_APP=['5'], READ_ONLY_SYSTEM_APP=['10'],
                CUSTOMER_ADMIN=['7', '6', '8'], USER=['6', '8'],
                READ_ONLY_USER=['6', '11'], APPLICATION=['8'],
                READ_ONLY_APPLICATION=['11'])

class RestException(Exception):

    def __init__(self, response):
        Exception.__init__(self, 'Status Code %d : %s'
                            % (response.status, response.reason))
        self.response = response

def getText(elem):
    rc = []
    for node in elem.childNodes:
        if node.nodeType == node.TEXT_NODE:
            rc.append(node.data)
    return str(''.join(rc))

class Result:
    
    def __init__(self, resources, start, remaining, total):
        self.start = start
        self.remaining = remaining
        self.total = total
        self.resources = resources
        
    def __iter__(self):
        return self.resources.__iter__()

class RestResource:
    def __init__(self, **attrs):
        for attr in attrs:
            setattr(self, attr, attrs[attr])
            
    def __str__(self):
        return str(self.__dict__)

    def fill_element(self, document, parent):
        """
        Adds corresponding minidom Elements of the attrs of this
        RestResource.  (Note: Recursive.)
        """
        for k in self.__dict__:
            values = self.__dict__[k]

            if not isinstance(values, list):
                values = [values]

            for value in values:
                element = document.createElement(k)
                if isinstance(value, RestResource):
                    value.fill_element(document,element)
                else:
                    if value: 
                        element.appendChild(document.createTextNode(value))
                parent.appendChild(element)

    def todocument(self):
        """
        Returns a minidom Document of this RestResource.
        """
        doc = impl.createDocument(None, type(self).__name__, None)
        root = doc.documentElement
        self.fill_element(doc,root)
        return doc

    @staticmethod
    def create(typename,**attrs):
        """
        Creates a RestResource with the given name and creates attrs out of
        the given kwargs.
        """
        resource = type(typename, (RestResource,object), {})
        return resource(**attrs)

def parse_elements(resource):
    attrs = {}
    for node in resource.childNodes:
        if isinstance(node,Element):
            k = str(node.nodeName)
            v = parse_node(node)
            if attrs.has_key(k):
                if type(attrs[k]) == list:
                    attrs[k].append(v)
                else:
                    attrs[k] = [attrs[k],v]
            else:
                attrs[k] = v
    return attrs
    

def parse_node(node):
    non_text_nodes = [child_node for child_node in node.childNodes \
                      if isinstance(child_node, Element)]

    if len(non_text_nodes) > 0:
        # Non-text nodes, parse into dict
        attrs = parse_elements(node)
        return RestResource.create(str(node.nodeName), **attrs)
    else:
        return getText(node)

def parse_response(response, resource):
    doc = parseString(response)
    resource_elem = doc.documentElement
    resource_name = str(resource_elem.nodeName)
    resources = []

    # if the resource name is result there were multiple entries,
    # return array.
    if resource_name == 'result':
        start = parse_node(
                    resource_elem.getElementsByTagName("requestedStartRow")[0])
        remaining = parse_node(
                        resource_elem.getElementsByTagName("remainingSize")[0])
        total = parse_node(
                    resource_elem.getElementsByTagName("resultTotalRows")[0])
        
        resources = [node for node in resource_elem.childNodes]
        resource_objs = []
        for resource_elem in resources:
            resource_name = str(resource_elem.nodeName)
            if isinstance(resource_elem, Element) and \
                   resource_name == resource or \
                   (resource_name == "User" and resource == "RawUser"):
                resource_type = type(resource_name, (RestResource,object), {})
                attrs = parse_elements(resource_elem)
                resource_objs.append(resource_type(**attrs))
        result = Result(resource_objs, start, remaining, total)
        return result
    # Otherwise, this is a single entry, just return it.
    else:
        resource = type(resource_name, (RestResource,object), {})
        attrs = dict((str(node.nodeName), getText(node))
                     for node in resource_elem.childNodes)
        return resource(**attrs)

class Api:
    
    def __init__(self, username, password,
                 hostname='developer.idigi.com', ws_root='/ws', 
                 content_type='text/xml', cst_id=None, usr_id=None):
        self.hostname = hostname
        self.ws_root = ws_root
        self.cst_id = cst_id
        self.usr_id = usr_id
        self.headers = {
            'Content-Type' : '%s' % content_type,
            'Authorization': 'Basic ' \
            + encodestring('%s:%s' % (username,password))[:-1]
        }
    
    def sci(self, request):
        """
        Posts an SCI request (RCI, update firmware, messaging facility to 
        /ws/sci.
        
        Arguments:
        request: The full SCI string to send.
        """
        connection = httplib.HTTPConnection(self.hostname)
        url = '%s/sci' % self.ws_root
        
        connection.request('POST', url, request, self.headers)
        response = connection.getresponse()
        response_str = response.read()
        connection.close()

        if response.status == 202 or response.status == 201 or \
            response.status == 200:
            return response_str
        else:
            raise RestException(response)        
    
    def sci_expect_fail(self, request):
        """
        Posts an SCI request (RCI, update firmware, messaging facility to 
        /ws/sci.
        
        Arguments:
        request: The full SCI string to send.
        """
        connection = httplib.HTTPConnection(self.hostname)
        url = '%s/sci' % self.ws_root
        
        connection.request('POST', url, request, self.headers)
        response = connection.getresponse()
        response_str = response.read()
        connection.close()

        return response_str
 

    def sci_status(self, jobId):
    
        connection = httplib.HTTPConnection(self.hostname)
        url = '%s/sci/%s' % (self.ws_root, jobId)
        
        log.info("Performing GET on %s" % url)
        
        connection.request('GET', url, headers = self.headers)
        
        response = connection.getresponse()
        response_str = response.read()
        connection.close()
        
        if response.status == 200:
            return response_str
        else:
            raise RestException(response)
        
        
    def get(self, resource, **params):
        connection = httplib.HTTPConnection(self.hostname)
        url = '%s/%s' % (self.ws_root, resource)

        if params:
            url += '?' + urllib.urlencode([(key,params[key]) for key in params])

        connection.request('GET', url,
                           headers = self.headers)
        
        log.info("Sending GET to %s" %url)
        response = connection.getresponse()
        response_str = response.read()
        connection.close()

        if response.status == 200:
            response = parse_response(response_str, resource.split('/')[0])
            return response
        else:
            raise RestException(response)
                            
    def get_raw(self, resource, **params):
        warnings.warn('get_raw is deprecated.  Please use get instead.', 
            DeprecationWarning)
        connection = httplib.HTTPConnection(self.hostname)
        url = '%s/%s' % (self.ws_root, resource)
        
        if params:
            url += '?' + urllib.urlencode([(key,params[key]) for key in params])
        
        connection.request('GET', url, headers = self.headers)
        
        log.info("Sending GET to %s" %url)
        response = connection.getresponse()
        response_str = response.read()
        connection.close()
        
        if response.status == 200:
            return response_str
            
        else:
            raise RestException(response)
                             
    def get_first(self, resource, **params):
        result = self.get(resource, **params)
        if result and result.resources:
            return result.resources[0]

        # No matches return nothing
        return None
            
    def __update(self, resource, method, **params):
        connection = httplib.HTTPConnection(self.hostname)
        request = resource.todocument()
        if hasattr(resource, 'location'):
            target = resource.location
        else:
            target = type(resource).__name__
            if target == "User":
                target = "RawUser"
        
        log.info("%s to %s with: %s." % (method, target, resource))
        
        url = '%s/%s' % (self.ws_root, target)
        if params:
            url += '?' + urllib.urlencode([(key,params[key]) for key in params])
            
        connection.request(method, url,
                           request.toxml(), self.headers)
        response = connection.getresponse()
        response_str = response.read()
        connection.close()
        if response.status == 201 or response.status == 200:
            location = response.getheader('Location')
            return location
        else:
            raise RestException(response)

    def post(self, resource, **params):
        return self.__update(resource, 'POST', **params)

    def post_raw(self, resource, content):
        warnings.warn('post_raw is deprecated.  Please use post instead.', 
            DeprecationWarning)
        connection = httplib.HTTPConnection(self.hostname)
        
        url = '%s/%s' % (self.ws_root, resource)
        
        log.info("POST to %s" % (resource))
        connection.request('POST', url, content, self.headers)
        
        response = connection.getresponse()
        response_str = response.read()
        connection.close()
        
        
        if response.status == 202 or response.status == 201 \
            or response.status == 200:
            return response_str
        else:
            raise RestException(response)
        
    def put(self, resource, **params):
        return self.__update(resource, 'PUT', **params)

    def put_raw(self, resource, content, **params):
        warnings.warn('put_raw is deprecated.  Please use put instead.', 
            DeprecationWarning)

        connection = httplib.HTTPConnection(self.hostname)
        
        url = '%s/%s' % (self.ws_root, resource)
        
        if params:
            url += '?' + urllib.urlencode([(key,params[key]) for key in params])
             
        if content:
            log.info("PUT to %s" % (resource))
            connection.request('PUT', url, content, self.headers)
        else:
            connection.request('PUT', url, self.headers)
                
        response = connection.getresponse()
        response_str = response.read()
        connection.close()

        if response.status == 202 or response.status == 201 \
            or response.status == 200:
            return response_str
        else:
            raise RestException(response)
    
    def delete(self, resource):
        if resource.location:
            return self.delete_location(resource.location)
        else:
            raise Exception('Cannot DELETE as Resource has no location.')

    def delete_location(self, resource):
        log.info("DELETE on %s." % resource)
        connection = httplib.HTTPConnection(self.hostname)
        connection.request('DELETE', '%s/%s' % (self.ws_root, resource), \
                           '', self.headers)

        response = connection.getresponse()
        response_str = response.read()
        connection.close()

        if not response.status == 200:
            raise RestException(response)
                
    def get_rate_plan(self, name, description=None):
        
        condition = "svcName='%s'" % name
        if description is not None:
            condition = "%s and svcDescription='%s'" % (condition, description)
        
        service = self.get_first('Service', 
                    condition=condition)
                    
        rate_plans = self.get('RatePlan', 
                        condition="svcId='%s'" % service.id.svcId)
        
        return_plan = None
        # Grab the Rate Plan with the largest rpLimit.
        for rate_plan in rate_plans:
            if return_plan is None or\
                int(rate_plan.rpLimit) > int(return_plan.rpLimit):
                return_plan = rate_plan
        
        return return_plan
        
    def create_account(self):
        """
        Uses /ws/Account to create a Customer Account with a UUID based 
        Company Name.  Additionally creates a UUID based User Name and 
        Service Contract for Device 
        Management, Web Service Messaging, and Device Messaging.
        
        Returns an Api instance for the created User.
        """
        
        # UUID used for tying Customers, Users and Contracts.
        cust_uuid = uuid.uuid4().hex[0:30]

        # Create Account using Account Web Service
        customer = RestResource.create('Customer', 
            cstCompanyName='Rest Api Created Account',
            cstNumber = cust_uuid)

        user = RestResource.create('User', usrUserName=cust_uuid, 
            usrPassword='ZAQ!2wsx', usrEmail='atolber@digi.com')

        # Add the Management Rate Plan at the very least.
        mgmt_rate_plan = self.get_rate_plan('management')

        management_contract_plan = RestResource.create('ContractPlan', 
            rpAutoSubscribe='true',
            id = RestResource.create('id', rpId=mgmt_rate_plan.id.rpId, 
                                        rpVersion='0'))
                                        
        
        ws_rate_plan = self.get_rate_plan('messaging', 
            'iDigi WebService messaging')
        
        ws_contract_plan =RestResource.create('ContractPlan',
            rpAutoSubscribe='true',
            id = RestResource.create('id', rpId=ws_rate_plan.id.rpId,
                                        rpVersion='0'))

        contract_plans = RestResource.create('contractPlans', 
            ContractPlan=[management_contract_plan, ws_contract_plan])

        service_contract = RestResource.create('ServiceContract', 
            scName=cust_uuid, contractPlans=contract_plans)

        account = RestResource.create('Account', Customer=customer,
            User=user, ServiceContract=service_contract)

        # Post Returns a Location formatted like Account/cstId/usrId/scId
        # Parse out the usrId and Retrieve it and then create an 
        # API from it.
        location = self.post(account)
        matcher = re.match('Account/(\d+)/(\d+)/(\d+)', location)
        cst_id = matcher.group(1)
        usr_id = matcher.group(2)
        
        user = self.get_first('User/%s' % usr_id)
        api = Api(user.usrUserName, 'ZAQ!2wsx', hostname=self.hostname, 
                    ws_root=self.ws_root, cst_id=cst_id, usr_id=usr_id)
        
        return api