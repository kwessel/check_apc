#!/usr/bin/env python3

import sys
import re
import argparse
import subprocess
from subprocess import CalledProcessError

class PluginUnknownException(Exception):
    pass

def getAPCInfo():
    try:
        result = subprocess.run(["/sbin/apcaccess", "status"], capture_output=True, check=True)
    except CalledProcessError as e:
        raise PluginUnknownException(f"Apcaccess command exited with error {e.returncode}")
    except Exception as e:
        raise PluginUnknownException(f"Failed to run apcaccess: {e}")

    apcdict = {}
    for line in result.stdout.decode('utf-8').splitlines():
        if ":" in line:
            k,v = line.split(":", maxsplit=1)
            apcdict[k.strip()] = v.strip()

    return(apcdict)

def getValue(info, key, isFloat=False):
    try:
        if isFloat:
            return(float(re.findall(r'[-+]?[0-9]*\.?[0-9]*', info[key])[0]))
        else:
            return(info[key])
    except exception as e:
        raise PluginUnknownException(f"No value for {key} available from apcaccess: {e}")

def checkValue(val, warn, crit, threshold_is_minimum=True):
    if threshold_is_minimum:
        if crit and val < crit:
            return(2)
        elif warn and val < warn:
            return(1)
        else:
            return(0)

    else:
        if crit and val > crit:
            return(2)
        elif warn and val > warn:
            return(1)
        else:
            return(0)

def stateText(state):
    if state == 3: return "UNKNOWN"
    elif state == 2: return "CRITICAL"
    elif state == 1: return "WARNING"
    else: return "OK"

def parseCommandLine():
    parser = argparse.ArgumentParser(
        description="Monitor an APC UPS using apcaccess",
        )

    parser.add_argument("-o", "--online", dest="online", default=False,
                        action="store_true",
                        help="always return OK if UPS is not on battery")

    charge_opts = parser.add_argument_group("Battery charge options")

    charge_opts.add_argument("-c", "--charge-warn", dest="chargewarn", type=float,
                        action="store", metavar="percent",
                        help="battery charge warning threshold")

    charge_opts.add_argument("-C", "--charge-crit", dest="chargecrit", type=float,
                        action="store", metavar="percent",
                        help="battery charge critical threshold")

    runtime_opts = parser.add_argument_group("Battery runtime options")

    runtime_opts.add_argument("-r", "--runtime-warn", dest="timewarn", type=float,
                        action="store", metavar="mins",
                        help="battery runtime warning threshold")

    runtime_opts.add_argument("-R", "--runtime-crit", dest="timecrit", type=float,
                        action="store", metavar="mins",
                        help="battery runtime critical threshold")

    voltage_opts = parser.add_argument_group("Battery voltage")

    voltage_opts.add_argument("-v", "--voltage-warn", dest="voltwarn", type=float,
                        action="store", metavar="voltage",
                        help="battery voltage warning threshold")

    voltage_opts.add_argument("-V", "--voltage-crit", dest="voltcrit", type=float,
                        action="store", metavar="voltage",
                        help="battery voltage critical threshold")

    #parse arguments
    options = parser.parse_args()

    if options.chargewarn and (options.chargewarn < 0 or options.chargewarn > 100):
        raise UnknownPluginException(f"Percent battery warning threshold must be between 0 and 100, value was {options.chargewarn}")

    if options.chargecrit and (options.chargecrit < 0 or options.chargecrit > 100):
        raise UnknownPluginException(f"Percent battery critical threshold must be between 0 and 100, value was {options.chargecrit}")

    return(options)

if __name__ == "__main__":
    try:
        # Parse command line
        options = parseCommandLine()

        # Read status from UPS
        apcinfo = getAPCInfo()

        # Are we on battery instead of wall power?
        on_batt = getValue(apcinfo, "TONBATT", True) > 0

        # if -o specified, return OK regardless of warn/crit thresholds
        always_ok = options.online and not on_batt

        status = 0
        text = ["on battery"] if on_batt else ["online"]
        perfdata = []

        # Are we testing battery percentage
        if options.chargewarn or options.chargecrit:
            charge = getValue(apcinfo, "BCHARGE", True)
            text.append(f"charge: {charge}%")
            perfdata.append(f"charge={charge}%")
            if not always_ok:
                new_status = checkValue(charge, options.chargewarn, options.chargecrit)
                status = new_status if new_status > status else status

        # Are we testing battery runtime
        if options.timewarn or options.timecrit:
            runtime = getValue(apcinfo, "TIMELEFT", True)
            text.append(f"available runtime: {runtime} minutes")
            perfdata.append(f"runtime={runtime}")
            if not always_ok:
                new_status = checkValue(runtime, options.timewarn, options.timecrit)
                status = new_status if new_status > status else status

        # Are we testing battery voltage
        if options.voltwarn or options.voltcrit:
            volt = getValue(apcinfo, "BATTV", True)
            text.append(f"voltage: {volt}V")
            perfdata.append(f"voltage={volt}")
            if not always_ok:
                new_status = checkValue(volt, options.voltwarn, options.voltcrit)
                status = new_status if new_status > status else status

    except PluginUnknownException as e:
        print(f"UPS {stateText(3)} - {e}")
        sys.exit(3)

    # Only testing to see if UPS is on battery, set to crit if it is
    if on_batt and len(text) == 1 and not always_ok:
        status=2

    print(f"UPS {stateText(status)} - {', '.join(text)};", end="")

    if perfdata:
        print(f"| {','.join(perfdata)}", end="")

    print()

    sys.exit(status)
