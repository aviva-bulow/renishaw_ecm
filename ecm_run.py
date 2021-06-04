#!/usr/bin/python3
#
# Run a local measurement template on a remote WiRE system using the externally
# controlled measurement interface.

from __future__ import print_function, absolute_import, division
import sys, requests, json, time, argparse


class ECMException(Exception):
    def __init__(self, message):
        super(ECMException, self).__init__(message)
        self.message = message


class ECMConnection:
    def __init__(self, url):
        self.url = url
        self._id = 0
        self.headers = {"content-type": "application/json"}

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
        result = None
        data = dict(jsonrpc="2.0", id=self.id, method=methodName, params=kwargs)
        res = requests.post(
            self.url,
            headers=self.headers,
            json=data,
            timeout=0.2,
            proxies={"http": None},
        )
        if res.status_code == requests.codes.ok:
            r = json.loads(res.text)
            if "error" in r:
                raise ECMException(r["error"]["message"])
            else:
                result = r["result"]
        else:
            print(res)
            raise ECMException(res.text)
        return result

    def wait(self, handle, timeout=10000):
        """
        Wait for a specified measurement to complete with a timeout limit.
        If we timeout then the status result will not be "COMPLETE".
        """
        # Wait for the measurement status to change
        # time.sleep(0.250)
        status = ""
        while status != "COMPLETE" and timeout > 0:
            try:
                status = self.call("Queue.GetMeasurementState", handle=handle)
            except ECMException as ex:
                print(ex)
            time.sleep(0.250)
            timeout -= 250
        return status


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    # Define the command line parameters.
    parser = argparse.ArgumentParser(
        description="Run a WiRE measurement using the JSON-RPC API"
    )
    parser.add_argument(
        "--url",
        dest="url",
        default="http://localhost:9880/api",
        help="URL for the API endpoint eg: http://hostname:9880/api",
    )
    parser.add_argument(
        "--template",
        dest="template",
        required=True,
        help="path of the measurement template to run",
    )
    parser.add_argument(
        "--filename",
        dest="filename",
        help="the filename for the data file (on the remote end)",
    )
    parser.add_argument(
        "--exposure", dest="exposure", type=int, help="exposure time in milliseconds"
    )
    parser.add_argument(
        "--accumulations",
        dest="accumulations",
        type=int,
        help="set the number of accumulations for the measurement",
    )
    parser.add_argument(
        "--get-laserpowers",
        dest="get_laserpowers",
        action="store_true",
        help="return the list of available laser power settings for the measurement",
    )
    parser.add_argument(
        "--laser-power",
        dest="power",
        type=float,
        help="set the measurement laser power. See also --get-laserpowers.",
    )
    options = parser.parse_args(args)

    # Open a connection to the WiRE system
    ecm = ECMConnection(options.url)

    # Load the local measurement template file
    with open(options.template) as f:
        template_xml = f.read()

    # Create a new measurement on the remote system in the paused state
    handle = ecm.call("Queue.Add", paused=True, monitor=False, wxmString=template_xml)

    # Set the exposure time on the remote measurement if defined
    if not options.exposure is None:
        ok = ecm.call(
            "Measurement.SetExposure", handle=handle, exposure=options.exposure
        )

    # Set the data filename on the remote measurement
    if not options.filename is None:
        data_path = ecm.call(
            "Measurement.SetFilename", handle=handle, filename=options.filename
        )

    # Set the number of accumulations to do in the remote measurement if defined.
    if not options.accumulations is None:
        ok = ecm.call(
            "Measurement.SetAccumulations",
            handle=handle,
            accumulations=options.accumulations,
        )
        ecm.Measurement.SetAccumulation(handle, 10)

    if not options.power is None:
        ok = ecm.call("Measurement.SetLaserPower", handle=handle, power=options.power)

    if options.get_laserpowers:
        powers = ecm.call("Measurement.GetLaserPowers", handle=handle)
        print(powers)
        ecm.call("Queue.Remove", handle=handle)
        return 0

    # Release the measurement to run on the remote system
    ok = ecm.call("Queue.Continue", handle=handle)

    # Wait for the measurement to complete
    status = ecm.wait(handle=handle)
    if status != "COMPLETE":
        print(
            "timed-out waiting with status '{0}'. Aborting.".format(status),
            file=sys.stderr,
        )
        ecm.call("Queue.Abort", handle=handle)
        time.sleep(0.500)

    # Remove the measurement once completed.
    ecm.call("Queue.Remove", handle=handle)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
