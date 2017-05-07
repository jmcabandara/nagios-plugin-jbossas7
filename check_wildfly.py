#!/usr/bin/env python3

#
# A Wildfly  Nagios check script
#
# https://github.com/mzupan/nagios-plugin-mongodb is used as a reference for this.

#
# Main Author
#   - Aparna Chaudhary <aparna.chaudhary@gmail.com>
#   - Gregor Tudan <gregor.tudan@cofinpro.de>
# Version: 0.3
#
# USAGE
#
# See the README.asciidoc
#

import sys
import time
import optparse
import re
import os
import requests
import logging
from requests.auth import HTTPDigestAuth

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError as e:
        print(e)
        sys.exit(2)


#
# TODO: Document
#
def optional_arg(arg_default):
    def func(option, opt_str, value, parser):
        if parser.rargs and not parser.rargs[0].startswith('-'):
            val = parser.rargs[0]
            parser.rargs.pop(0)
        else:
            val = arg_default
        setattr(parser.values, option.dest, val)
    return func

#
# TODO: Document
#
def performance_data(perf_data, params):
    data = ''
    if perf_data:
        data = " |"
        for p in params:
            p += (None, None, None, None)
            param, param_name, warning, critical = p[0:4]
            data += "%s=%s" % (param_name, str(param))
            if warning or critical:
                warning = warning or 0
                critical = critical or 0
                data += ";%s;%s" % (warning, critical)
                
            data += " "
            
    return data


def numeric_type(param):
    """
    Checks parameter type
    True for float; int or null data; false otherwise
    
    :param param: input param to check
    """
    if ((type(param) == float or type(param) == int or param == None)):
        return True
    return False


def check_levels(param, warning, critical, message, ok=[]):
    """
    Checks error level
    
    :param param: input param
    :param warning: watermark for warning
    :param critical: watermark for critical
    :param message: message to be reported to nagios
    :param ok: watermark for ok level
    """
    if (numeric_type(critical) and numeric_type(warning)):
        if param >= critical:
            print("CRITICAL - " + message)
            sys.exit(2)
        elif param >= warning:
            print( "WARNING - " + message)
            sys.exit(1)
        else:
            print("OK - " + message)
            sys.exit(0)
    else:
        if param in critical:
            print("CRITICAL - " + message)
            sys.exit(2)

        if param in warning:
            print("WARNING - " + message)
            sys.exit(1)

        if param in ok:
            print("OK - " + message)
            sys.exit(0)

        # unexpected param value
        print("CRITICAL - Unexpected value : %d" % param + "; " + message)
        return 2


def get_digest_auth_json(uri, payload):
    """
    HTTP GET with Digest Authentication. Returns JSON result.
    Base URI of http://{host}:{port}/management is used
    
    :param uri: URL fragment
    :param payload: URL parameter payload
    """
    try:
        url = base_url(host, port) + uri
        res = requests.get(url, params=payload, auth=HTTPDigestAuth(user, password))
        data = res.json()
        
        try:    
            outcome = data['outcome']
            if outcome == "failed":
                print("CRITICAL - Unexpected value : %s" % data)
                sys.exit(2)
        except KeyError: pass

        return data
    except Exception as e:
        # The server could be down; make this CRITICAL.
        print("CRITICAL - JbossAS Error:", e)
        sys.exit(2)


def post_digest_auth_json(uri, payload):
    """
    HTTP POST with Digest Authentication. Returns JSON result.
    Base URI of http://{host}:{port}/management is used
    
    :param uri: URL fragment
    :param payload: JSON payload 
    """
    try:
        url = base_url(host, port) + uri
        headers = {'content-type': 'application/json'}        
        res = requests.post(url, data=json.dumps(payload), headers=headers, auth=HTTPDigestAuth(user, password))
        data = res.json()
        
        try:    
            outcome = data['outcome']
            if outcome == "failed":
                print("CRITICAL - Unexpected value : %s" % data)
                sys.exit(2)
        except KeyError: pass

        return data
    except Exception as e:
        # The server could be down; make this CRITICAL.
        print("CRITICAL - JbossAS Error:", e)
        sys.exit(2)


def base_url(host, port):
    """
    Provides base URL for HTTP Management API
    
    :param host: JBossAS hostname
    :param port: JBossAS HTTP Management Port
    """
    url = "http://{host}:{port}/management".format(host=host, port=port)
    return url

def debug_log():
    """
    Enables request logging
    """

    import http.client as http_client
    http_client.HTTPConnection.debuglevel = 1
    
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

def main(argv):
    logging.basicConfig()
    logging.getLogger().setLevel(logging.ERROR)
    # debug_log() 
    global ds_stat_types
    ds_stat_types = ['ActiveCount', 'AvailableCount', 'AverageBlockingTime', 'AverageCreationTime',
                     'CreatedCount', 'DestroyedCount', 'MaxCreationTime', 'MaxUsedCount',
                     'MaxWaitTime', 'TimedOut', 'TotalBlockingTime', 'TotalCreationTime']

    actions = ['server_status', 'heap_usage', 'non_heap_usage', 'eden_space_usage',
                'old_gen_usage', 'perm_gen_usage', 'code_cache_usage', 'gctime',
                'queue_depth', 'datasource', 'xa_datasource', 'threading']
    
    p = optparse.OptionParser(conflict_handler="resolve", description="This Nagios plugin checks the health of JBossAS.")

    p.add_option('-H', '--host', action='store', type='string', dest='host', default='127.0.0.1', help='The hostname you want to connect to')
    p.add_option('-P', '--port', action='store', type='int', dest='port', default=9990, help='The port JBoss management console is runnung on')
    p.add_option('-u', '--user', action='store', type='string', dest='user', default=None, help='The username you want to login as')
    p.add_option('-p', '--pass', action='store', type='string', dest='passwd', default=None, help='The password you want to use for that user')
    p.add_option('-M', '--mode', action="store", type='choice', dest='mode', default='standalone', help='The mode the server is running', choices=['standalone', 'domain'])
    p.add_option('-n', '--node', action='store', type='string', dest='node', default=None, help='The wildfly node (host) this server is running (domain mode)')
    p.add_option('-i', '--instance', action='store', type='string', dest='instance', default=None, help='The wildfly instance (server-config) to check (domain mode)')
    p.add_option('-W', '--warning', action='store', dest='warning', default=None, help='The warning threshold we want to set')
    p.add_option('-C', '--critical', action='store', dest='critical', default=None, help='The critical threshold we want to set')
    p.add_option('-A', '--action', action='store', type='choice', dest='action', default='server_status', help='The action you want to take', choices=actions)
    p.add_option('-D', '--perf-data', action='store_true', dest='perf_data', default=False, help='Enable output of Nagios performance data')
    p.add_option('-m', '--memorypool', action='store', dest='memory_pool', default=None, help='The memory pool type')
    p.add_option('-q', '--queuename', action='store', dest='queue_name', default=None, help='The queue name for which you want to retrieve queue depth')
    p.add_option('-d', '--datasource', action='store', dest='datasource_name', default=None, help='The datasource name for which you want to retrieve statistics')
    p.add_option('-s', '--poolstats', action='store', dest='ds_stat_type', default=None, help='The datasource pool statistics type')
    p.add_option('-t', '--threadstats', action='store', dest='thread_stat_type', default=None, help='The threading statistics type')

    global host, port, user, password, node, instance, is_domain

    options, arguments = p.parse_args()
    host = options.host
    port = options.port
    user = options.user
    password = options.passwd
    instance = options.instance
    node = options.node
    mode = options.mode
    memory_pool = options.memory_pool
    queue_name = options.queue_name
    datasource_name = options.datasource_name
    ds_stat_type = options.ds_stat_type
    thread_stat_type = options.thread_stat_type

    is_domain = mode == 'domain'
    
    if (options.action == 'server_status'):
        warning = str(options.warning or "")
        critical = str(options.critical or "")
    else:
        warning = float(options.warning or 0)
        critical = float(options.critical or 0)

    action = options.action
    perf_data = options.perf_data

    if action == "server_status":
        return check_server_status(warning, critical, perf_data)
    elif action == "gctime":
        return check_gctime(memory_pool, warning, critical, perf_data)
    elif action == "queue_depth":
        return check_queue_depth(queue_name, warning, critical, perf_data)
    elif action == "heap_usage":
        return check_heap_usage(warning, critical, perf_data)
    elif action == "non_heap_usage":
        return check_non_heap_usage(warning, critical, perf_data)
    elif action == "eden_space_usage":
        return check_eden_space_usage(memory_pool, warning, critical, perf_data)
    elif action == "old_gen_usage":
        return check_old_gen_usage(memory_pool, warning, critical, perf_data)
    elif action == "perm_gen_usage":
        return check_perm_gen_usage(memory_pool, warning, critical, perf_data)
    elif action == "code_cache_usage":
        return check_code_cache_usage(memory_pool, warning, critical, perf_data)
    elif action == "datasource":
        return check_non_xa_datasource(datasource_name, ds_stat_type, warning, critical, perf_data)
    elif action == "xa_datasource":
        return check_xa_datasource(datasource_name, ds_stat_type, warning, critical, perf_data)
    elif action == "threading":
        return check_threading(thread_stat_type, warning, critical, perf_data)
    else:
        return 2


def exit_with_general_warning(e):
    """
    
    :param e: exception
    """
    if isinstance(e, SystemExit):
        return e
    elif isinstance(e, ValueError):
        print("WARNING - General JbossAS Error:", e)
        sys.exit(1)
    else:
        print("WARNING - General JbossAS warning:", e)
    return 1


def exit_with_general_critical(e):
    if isinstance(e, SystemExit):
        return e
    elif isinstance(e, ValueError):
        print("CRITICAL - General JbossAS Error:", e)
        sys.exit(2)
    else:
        print("CRITICAL - General JbossAS Error:", e)
    return 2


def check_server_status(warning, critical, perf_data):
    warning = warning or "reload-required"
    critical = critical or ""
    ok = "running"

    try:
        url = ''
        payload = {'operation': 'read-attribute', 'name': 'server-state'}
        if is_domain:
            payload['address'] = [{'host': node}, {'server': instance}]
        res = post_digest_auth_json(url, payload)
        res = res['result']
        
        message = "Server Status '%s'" % res
        message += performance_data(perf_data, [(res, "server_status", warning, critical)])
    
        return check_levels(res, warning, critical, message, ok)
    except Exception as e:
        return exit_with_general_critical(e)


def get_memory_usage(is_heap, memory_value):
    try:
        payload = {'include-runtime': 'true'}
        url = "/core-service/platform-mbean/type/memory"
        
        if is_domain:
            url = '/host/{}/server/{}'.format(node, instance) + url

        data = get_digest_auth_json(url, payload)
        
        if is_heap:
            data = data['heap-memory-usage'][memory_value] / (1024 * 1024)
        else:
            data = data['non-heap-memory-usage'][memory_value] / (1024 * 1024)
        
        return data
    except Exception as e:
        return exit_with_general_critical(e)

def check_heap_usage(warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90
    
    try:
        used_heap = get_memory_usage(True, 'used')
        max_heap = get_memory_usage(True, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)
        
        message = "Heap Memory Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "heap_usage", warning, critical)])
    
        return check_levels(percent, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)

def check_non_heap_usage(warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90
    
    try:
        used_heap = get_memory_usage(False, 'used')
        max_heap = get_memory_usage(False, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)
        
        message = "Non Heap Memory Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "non_heap_usage", warning, critical)])
    
        return check_levels(percent, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)

def get_memory_pool_usage(pool_name, memory_value):
    try:
        payload = {'include-runtime': 'true', 'recursive':'true'}
        url = "/core-service/platform-mbean/type/memory-pool"

        if is_domain:
            url = '/host/{}/server/{}'.format(node, instance) + url
        
        data = get_digest_auth_json(url, payload)
        usage = data['name'][pool_name]['usage'][memory_value] / (1024 * 1024)
        
        return usage
    except Exception as e:
        return exit_with_general_critical(e)


def check_eden_space_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90
    
    try:
        used_heap = get_memory_pool_usage(memory_pool, 'used')
        max_heap = get_memory_pool_usage(instance, memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)
        
        message = "Eden_Space Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "eden_space_usage", warning, critical)])
    
        return check_levels(percent, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)

def check_old_gen_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90
    
    try:
        used_heap = get_memory_pool_usage(memory_pool, 'used')
        max_heap = get_memory_pool_usage(memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)
        
        message = "Old_Gen Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "old_gen_usage", warning, critical)])
    
        return check_levels(percent, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)


def check_perm_gen_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 90
    critical = critical or 95
    
    try:
        used_heap = get_memory_pool_usage(memory_pool, 'used')
        max_heap = get_memory_pool_usage(memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)
        
        message = "Perm_Gen Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "perm_gen_usage", warning, critical)])
    
        return check_levels(percent, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)

def check_code_cache_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 90
    critical = critical or 95
    
    try:
        if memory_pool == None:
            memory_pool = 'Code_Cache'
        
        used_heap = get_memory_pool_usage(memory_pool, 'used')
        max_heap = get_memory_pool_usage(memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)
        
        message = "Code_Cache Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "code_cache_usage", warning, critical)])
    
        return check_levels(percent, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)


def check_gctime(memory_pool, warning, critical, perf_data):
    # Make sure you configure right values for your application    
    warning = warning or 500
    critical = critical or 1000
    
    try:
        payload = {'include-runtime': 'true', 'recursive':'true'}
        url = "/core-service/platform-mbean/type/garbage-collector"

        if is_domain:
            url = '/host/{}/server/{}'.format(node, instance) + url
        
        res = get_digest_auth_json(url, payload)
        gc_time = res['name'][memory_pool]['collection-time']
        gc_count = res['name'][memory_pool]['collection-count']
        
        avg_gc_time = 0
         
        if gc_count > 0:
            avg_gc_time = float(gc_time / gc_count)
        
        message = "GC '%s' total-time=%dms count=%s avg-time=%.2fms" % (memory_pool, gc_time, gc_count, avg_gc_time)
        message += performance_data(perf_data, [("%.2fms" % avg_gc_time, "gctime", warning, critical)])
    
        return check_levels(avg_gc_time, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)
    

def check_threading(thread_stat_type, warning, critical, perf_data):
    warning = warning or 100
    critical = critical or 200
    
    try:
        if thread_stat_type not in ['thread-count', 'peak-thread-count', 'total-started-thread-count', 'daemon-thread-count']:
            return exit_with_general_critical("The thread statistics value type of '%s' is not valid" % thread_stat_type)
            
        payload = {'include-runtime': 'true'}
        url = "/core-service/platform-mbean/type/threading"
        
        if is_domain:
            url = '/host/{}/server/{}'.format(node, instance) + url

        data = get_digest_auth_json(url, payload)
        data = data[thread_stat_type]
        
        message = "Threading Statistics '%s':%s " % (thread_stat_type, data)
        message += performance_data(perf_data, [(data, "threading", warning, critical)])
    
        return check_levels(data, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)


def check_queue_depth(queue_name, warning, critical, perf_data):
    warning = warning or 100
    critical = critical or 200
    
    try:    
        if queue_name is None:
            return exit_with_general_critical("The queue name '%s' is not valid" % queue_name)
            
        payload = {'include-runtime': 'true', 'recursive':'true'}
        url = "/subsystem/messaging/hornetq-server/default/jms-queue/" + queue_name

        if is_domain:
            url = '/host/{}/server/{}'.format(node, instance) + url
        
        data = get_digest_auth_json(url, payload)
        queue_depth = data['message-count']
        
        message = "Queue %s depth %s" % (queue_name, queue_depth)
        message += performance_data(perf_data, [(queue_depth, "queue_depth", warning, critical)])
    
        return check_levels(queue_depth, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)

def get_datasource_stats(is_xa, ds_name, ds_stat_type):
    try:    
        if ds_name is None:
            return exit_with_general_critical("The ds_name name '%s' is not valid" % ds_name)
        if ds_stat_type not in ds_stat_types:
            return exit_with_general_critical("The datasource statistics type of '%s' is not valid" % ds_stat_type)
            
        payload = {'include-runtime': 'true', 'recursive':'true'}
        if is_xa:
            url = "/subsystem/datasources/xa-data-source/" + ds_name + "/statistics/pool/"
        else:
            url = "/subsystem/datasources/data-source/" + ds_name + "/statistics/pool/"
        
        if is_domain:
            url = '/host/{}/server/{}'.format(node, instance) + url

        data = get_digest_auth_json(url, payload)
        data = data[ds_stat_type]
        
        return data
    except Exception as e:
        return exit_with_general_critical(e)


def check_non_xa_datasource(ds_name, ds_stat_type, warning, critical, perf_data):
    warning = warning or 0
    critical = critical or 10
    
    try:    
        data = get_datasource_stats(False, ds_name, ds_stat_type)
        
        message = "DataSource %s %s" % (ds_stat_type, data)
        message += performance_data(perf_data, [(data, "datasource", warning, critical)])
        return check_levels(data, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)

def check_xa_datasource(ds_name, ds_stat_type, warning, critical, perf_data):
    warning = warning or 0
    critical = critical or 10
    
    try:    
        data = get_datasource_stats(True, ds_name, ds_stat_type)

        message = "XA DataSource %s %s" % (ds_stat_type, data)
        message += performance_data(perf_data, [(data, "xa_datasource", warning, critical)])
        return check_levels(data, warning, critical, message)
    except Exception as e:
        return exit_with_general_critical(e)

def build_file_name(host, action):
    # done this way so it will work when run independently and from shell
    module_name = re.match('(.*//*)*(.*)\..*', __file__).group(2)
    return "/tmp/" + module_name + "_data/" + host + "-" + action + ".data"


def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)


def write_values(file_name, string):
    f = None
    try:
        f = open(file_name, 'w')
    except IOError as e:
        # try creating
        if (e.errno == 2):
            ensure_dir(file_name)
            f = open(file_name, 'w')
        else:
            raise IOError(e)
    f.write(string)
    f.close()
    return 0


def read_values(file_name):
    data = None
    try:
        f = open(file_name, 'r')
        data = f.read()
        f.close()
        return 0, data
    except IOError as e:
        if (e.errno == 2):
            # no previous data
            return 1, ''
    except Exception as e:
        return 2, None


def calc_delta(old, new):
    delta = []
    if (len(old) != len(new)):
        raise Exception("unequal number of parameters")
    for i in range(0, len(old)):
        val = float(new[i]) - float(old[i])
        if val < 0:
            val = new[i]
        delta.append(val)
    return 0, delta


def maintain_delta(new_vals, host, action):
    file_name = build_file_name(host, action)
    err, data = read_values(file_name)
    old_vals = data.split(';')
    new_vals = [str(int(time.time()))] + new_vals
    delta = None
    try:
        err, delta = calc_delta(old_vals, new_vals)
    except:
        err = 2
    write_res = write_values(file_name, ";" . join(str(x) for x in new_vals))
    return err + write_res, delta


#
# main app
#
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
