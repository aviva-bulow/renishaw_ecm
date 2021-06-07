#!/usr/bin/python3
#
# Run a local measurement template on a remote WiRE system using the externally
# controlled measurement interface.

from __future__ import print_function, absolute_import, division
import sys, os, requests, json, time, argparse, base64
from PIL import Image, ExifTags

# Custom EXIF tags
ExifTags.TAGS[0xfea0] = 'Position'
ExifTags.TAGS[0xfea1] = 'Field of view (1x)'
ExifTags.TAGS[0xfea2] = 'Objective'
ExifTags.TAGS[0xfea3] = 'LUTLimits'

class ECMException(Exception):
    def __init__(self, message):
        super(ECMException, self).__init__(message)
        self.message = message

class ECMConnection():
    def __init__(self, url):
        self.url = url
        self._id = 0
        self.debug = False
        self.headers = {'Content-Type': 'application/json'}

    @property
    def id(self):
        """
        Each JSON-RPC call gets a unique identifier by calling this property.
        """
        id = self._id
        self._id += 1
        return id

    def call(self, methodName, **kwargs):
        """
        Generic JSON-RPC method calling for the ECM API.
        """
        if self.debug and methodName != "Queue.GetMeasurementState":
            print ("Sent = " + methodName + " command.")
        result = None
        data = dict(jsonrpc="2.0", id=self.id, method=methodName, params=kwargs)
        res = requests.post(self.url, headers=self.headers, json=data, proxies={'http': None})
        # res.timeout = 1.0
        if res.status_code == requests.codes.ok:
            r = json.loads(res.text)
            if 'error' in r:
                raise ECMException(r['error']['message'])
            else:
                result = r['result']
        else:
            raise ECMException(res.text)
        return result

    def wait(self, handle, timeout=10000):
        """
        Wait for a specified measurement to complete with a timeout limit.
        If we timeout then the status result will not be "COMPLETE".
        """
        # Wait for the measurement status to change
        time.sleep(0.250)
        status = ""
        while status != "COMPLETE" and timeout > 0:
            try:
                status = self.call("Queue.GetMeasurementState", handle=handle)
                if self.debug:
                    print("status: {0}".format(status))
            except ECMException as ex:
                print(ex)
            time.sleep(0.250)
            timeout -= 250
        return status

def parse_map(arg):
    """
    Takes a JSON collection with
      {"xStart": number, "yStart": number, "xStep": number, "yStep": number, "xCount": integer, "yCount": integer, "row_major": bool,"snake": bool  }}
    This returns an array of [xStart, yStart, xStep, yStep, xCount, yCount, row_major, snake]
    ready to be passed to the Measurement.SetMap function
    """
    param = json.loads(arg)
    return [param['xStart'], param['yStart'], param['xStep'], param['yStep'], param['xCount'], param['yCount'], param['row_major'], param['snake']]

def parse_series(arg):
    """
    Takes a JSON collection with
      {"count": integer, "start": number, "step": number, "units": string, "label": string}
    This returns an array of [count, start, step, units, label]
    ready to be passed to the Measurement.SetMap function
    """
    param = json.loads(arg)
    return [param['count'], param['start'], param['step'], param['units'], param['label']]

def parse_custom(arg):
    """
    Takes a JSON collection with
      {"index": integer, "type": string, "units": string, "label": string}
    This returns an array of [index, type, units, label]
    ready to be passed to Measurement.SetMapCustomAxis function
    """
    param = json.loads(arg)
    return [param['index'], param['type'], param['units'], param['label']]

def _exif_num(item):
    return float(item[0])/float(item[1])

def parse_whitelight(arg):
    """
    Opens a JPEG image and parses the EXIF data build the structure required by the JSON API
    """
    with open(arg, 'rb') as f:
        imagedata = f.read()
    imagedata = base64.b64encode(imagedata).decode('utf-8')
    img = Image.open(arg)
    exif = { (ExifTags.TAGS[k] if k in ExifTags.TAGS else hex(k)):v for k,v in img._getexif().items() }
    img.close()
    return {
        "Image": imagedata,
        "Objective": _exif_num(exif['Objective']),
        "XPosition": _exif_num(exif['Position'][0]),
        "YPosition": _exif_num(exif['Position'][1]),
        "XFieldOfView": _exif_num(exif['Field of view (1x)'][0]),
        "YFieldOfView": _exif_num(exif['Field of view (1x)'][1])
    }

def main(args = None):
    if args is None:
        args = sys.argv[1:]
    # Define the command line parameters.
    parser = argparse.ArgumentParser(description="Run a WiRE measurement using the JSON-RPC API")
    parser.add_argument('--url', dest='url', default='http://localhost:9880/api/',
        help='URL for the API endpoint eg: http://hostname:9880/api/')
    parser.add_argument('--template', dest='template',
        help='path of the measurement template to run')
    parser.add_argument('--filename', dest='filename',
        help='the filename for the data file (on the remote end)')
    parser.add_argument('--exposure', dest='exposure', type=int,
        help='exposure time in milliseconds')
    parser.add_argument('--accumulations', dest='accumulations', type=int,
        help='set the number of accumulations for the measurement')
    parser.add_argument('--get-laserpowers', dest='get_laserpowers', action='store_true',
        help='return the list of available laser power settings for the measurement')
    parser.add_argument('--laser-power', dest='power', type=float,
        help='set the measurement laser power. See also --get-laserpowers.')
    parser.add_argument('--whitelight', dest='whitelight', type=parse_whitelight,
        help='set the whitelight image from a JPEG file')
    parser.add_argument('--map-area', dest='map', type=parse_map,
        help='''configure the measurement as a map eg:
                {"xStart": number, "yStart": number, "xStep": integer, "yStep": integer, "xCount": integer, "yCount": integer, "row_major": bool, "snake": bool}
             ''')
    parser.add_argument('--series', dest='series', type=parse_series,
        help='''configure the measurement as a series. pass a JSON collection e.g.:
                  {"count": integer, "start": number, "step": number, "units": string, "label": string}
             ''')
    parser.add_argument('--custom', dest='custom', type=parse_custom,
        help='''add a custom data origin to the map or series e.g.:
                { "index": integer, "type": string, "units" : string, "label": string }
             ''')
    parser.add_argument('--use-client-stage', dest='stage', action='store_false',
        help='Specify use of the client stage')
    parser.add_argument('--use-wire-stage', dest='stage', action='store_true',
        help='Specify use of the WiRE stage')
    parser.add_argument('--enable-triggers', dest='triggers', action='store_true',
        help='enable trigger mode')
    parser.add_argument('--send-trigger', dest='send_trigger', type=int,
        help='send a trigger over TCP/IP. Parameter must the the measurement handle number.')
    parser.add_argument('--debug', dest='debug', action='store_true',
        help='enable additional debugging output')
    parser.add_argument('--timeout', dest='timeout', type=int, default=60000,
        help='specify the measurement timeout in milliseconds')
    options = parser.parse_args(args)

    # Open a connection to the WiRE system
    ecm = ECMConnection(options.url)
    if options.debug:
        ecm.debug = True

    if not options.send_trigger is None:
        ecm.call("Measurement.Trigger", handle=options.send_trigger)
        return 0

    # Load the local measurement template file
    with open(options.template) as f:
        template_xml = f.read()

    # Create a new measurement on the remote system in the paused state
    handle = ecm.call("Queue.Add", paused=True, monitor=False, wxmString=template_xml)

    # Set the exposure time on the remote measurement if defined
    if not options.exposure is None:
        ok = ecm.call("Measurement.SetExposure", handle=handle, exposure=options.exposure)

    # Set the data filename on the remote measurement
    if not options.filename is None:
        data_path = ecm.call("Measurement.SetFilename", handle=handle, filename=options.filename)

    # Set the number of accumulations to do in the remote measurement if defined.
    if not options.accumulations is None:
        ok = ecm.call("Measurement.SetAccumulations", handle=handle, accumulations=options.accumulations)

    # Set the laser power as a percentage if defined.
    if not options.power is None:
        ok = ecm.call("Measurement.SetLaserPower", handle=handle, power=options.power)

    # Print out the set of available laser powers and exit
    # note: we have to have a measurement loaded in to be able to call this.
    if options.get_laserpowers:
        powers = ecm.call("Measurement.GetLaserPowers", handle=handle)
        for value in powers:
            print("{0:.3g}".format(value))
        ecm.call("Queue.Remove", handle=handle)
        return 0

    # Add a whitelight image into the measurement.
    if not options.whitelight is None:
        ecm.call("Measurement.SetImage", handle=handle, **options.whitelight)

    # Define a map measurement...
    # We have a custom parser for the arguments passed to --map. See the help.
    if not options.map is None:
        ecm.call("Measurement.SetMap", handle=handle, rectangleParam=options.map)

    # Define a series measurement if --series was set.
    if not options.series is None:
        ecm.call("Measurement.SetMap", handle=handle, seriesParam=options.series)

    # Define any custom axes.
    if not options.custom is None:
        ecm.call("Measurement.SetMapCustomAxis", handle=handle, custom_axes=options.custom)

    # Specify the use of the wire or the client stage for mapping modes.
    if not options.stage is None:
        ecm.call("Measurement.SetMapUseStage", handle=handle, use_stage=options.stage)

    # Setup the trigger mode if requested.
    if options.triggers:
        ecm.call("Measurement.SetMapTriggerMode", handle=handle, mode="TCP_IP")

    # Release the measurement to run on the remote system
    ok = ecm.call("Queue.Continue", handle=handle)

    # Wait for the measurement to complete
    status = ecm.wait(handle=handle, timeout=options.timeout)
    if status != "COMPLETE":
        print("timed-out waiting with status '{0}'. Aborting.".format(status), file=sys.stderr)
        ecm.call("Queue.Abort", handle=handle)
        time.sleep(0.500)

    # Remove the measurement once completed.
    ecm.call("Queue.Remove", handle=handle)

    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
