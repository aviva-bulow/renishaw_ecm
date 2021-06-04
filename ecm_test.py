#!/usr/bin/python3
#
# Flog the queue ECM

from __future__ import print_function, absolute_import, division
import sys, requests, json, time, argparse

def main(args = None):
    if args is None:
        args = sys.argv[1:]
        
    parser = argparse.ArgumentParser(description="Test the WiREQueue JSON-RPC API")
    parser.add_argument('--url', dest='url', default='http://localhost:9880/api',
        help='URL for the API endpoint')
    parser.add_argument('--count', dest='count', type=int, default=100,
        help='number of requests to make')
    parser.add_argument('--method', dest='method', default='Queue.GetState',
        help='API method name')
    options = parser.parse_args(args)
    
    headers = {'content-type': 'application/json'}
    data = dict(jsonrpc="2.0", id=0, method=options.method, params=[])
    for id in range(0,options.count):
        data['id'] = id
        res = requests.post(options.url, headers=headers, json=data, timeout=0.2, proxies={'http': None})
        if res.status_code == requests.codes.ok:
            r = json.loads(res.text)
            if 'error' in r:
                print("{0}: error: {1}".format(id, r['error']['message']), file=sys.stderr)
            else:
                print("{0}: {1}".format(id, r['result']))
            sys.stdout.flush()
        else:
            print("error: {0}".format(res.text), file=sys.stderr)
        #time.sleep(0.05)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
