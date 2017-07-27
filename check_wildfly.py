#!/usr/bin/env python3

"""
A Nagios script for checking Wildfly/JBossAS over HTTP

 Main Author
   - Aparna Chaudhary <aparna.chaudhary@gmail.com>
   - Gregor Tudan <gregor.tudan@cofinpro.de>

USAGE

See the README.asciidoc

"""

import json
import logging
import optparse
import sys

import requests
from requests.auth import HTTPDigestAuth

CONFIG = dict({
    "host": "localhost",
    "port": 9990,
    "user": None,
    "mode": "standalone",
    "password": None,
    "node": None,
    "instance": None,
})

DS_STAT_TYPES = ['ActiveCount', 'AvailableCount', 'AverageBlockingTime', 'AverageCreationTime',
                 'CreatedCount', 'DestroyedCount', 'MaxCreationTime', 'MaxUsedCount',
                 'MaxWaitTime', 'TimedOut', 'TotalBlockingTime', 'TotalCreationTime']

THREAD_STAT_TYPES = ['thread-count', 'peak-thread-count', 'total-started-thread-count', 'daemon-thread-count']

ACTIONS = ['server_status', 'heap_usage', 'non_heap_usage', 'eden_space_usage',
           'old_gen_usage', 'perm_gen_usage', 'code_cache_usage', 'gc_time',
           'queue_depth', 'datasource', 'xa_datasource', 'threading', "deployment_status"]

NAGIOS_STATUS = {-1: 'UNKNOWN', 0: 'OK', 1: 'WARNING', 2: 'CRITICAL'}


#
# TODO: Document
#
def _optional_arg(arg_default):
    def func(option, parser):
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
def _performance_data(perf_data, params):
    if not perf_data:
        return ''

    data = ""
    for param in params:
        param += (None, None, None, None, None, None)
        param_value, param_name, warning, critical, min_value, max_value = param[0:6]
        data += "%s=%s" % (param_name, str(param_value))
        if warning or critical:
            warning = warning or 0
            critical = critical or 0
            data += ";%s;%s" % (warning, critical)
            if min_value is not None and max_value is not None:
                data += ";%s;%s" % (min_value, max_value)
        data += " "
    return data


def _numeric_type(param):
    """
    Checks parameter type
    True for float; int or null data; false otherwise

    :param param: input param to check
    """
    return isinstance(param, (float, int)) or param is None


def _check_levels(param, warning, critical, ok=None):
    """
    Checks error level

    :param param: input param
    :param warning: watermark for warning
    :param critical: watermark for critical
    :param message: message to be reported to nagios
    :param ok: watermark for ok level
    """

    if _numeric_type(critical) and _numeric_type(warning):
        if param >= critical != -1:
            return_code = 2
        elif param >= warning != -1:
            return_code = 1
        else:
            return_code = 0
    else:
        if param in critical:
            return_code = 2
        elif param in warning:
            return_code = 1
        elif ok is None or param in ok:
            return_code = 0
        else:
            return_code = -1

    return return_code


def _get_digest_auth_json(uri, payload):
    """
    HTTP GET with Digest Authentication. Returns JSON result.
    Base URI of http://{host}:{port}/management is used

    :param uri: URL fragment
    :param payload: URL parameter payload
    """
    try:
        url = _base_url(CONFIG['host'], CONFIG['port']) + uri
        auth = HTTPDigestAuth(CONFIG['user'], CONFIG['password'])
        res = requests.get(url, params=payload, auth=auth)
        res.raise_for_status()
        return res.json()

    except requests.HTTPError as exc:
        print("UNKNOWN:", exc)
        sys.exit(-1)


def _post_digest_auth_json(uri, payload):
    """
    HTTP POST with Digest Authentication. Returns JSON result.
    Base URI of http://{host}:{port}/management is used

    :param uri: URL fragment
    :param payload: JSON payload
    """
    try:
        url = _base_url(CONFIG['host'], CONFIG['port']) + uri
        headers = {'content-type': 'application/json'}
        auth = HTTPDigestAuth(CONFIG['user'], CONFIG['password'])
        res = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth)
        data = res.json()

        try:
            outcome = data['outcome']
            if outcome == "failed":
                print("CRITICAL - Unexpected value : %s" % data)
                sys.exit(2)
        except KeyError:
            pass

        return data
    except requests.HTTPError as exc:
        print("UNKNOWN:", exc)
        sys.exit(-1)


def _base_url(host, port):
    """
    Provides base URL for HTTP Management API
    :param host: JBossAS hostname
    :param port: JBossAS HTTP Management Port
    """
    return "http://{host}:{port}/management".format(host=host, port=port)


def _debug_log():
    """
    Enables request logging
    """

    import http.client as http_client
    http_client.HTTPConnection.debuglevel = 1

    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


def main():
    logging.basicConfig()
    logging.getLogger().setLevel(logging.ERROR)
    # _debug_log()

    parser = optparse.OptionParser(conflict_handler="resolve",
                                   description="This Nagios plugin checks the health of JBossAS.")

    parser.add_option('-H', '--host', action='store', type='string', dest='host', default='127.0.0.1',
                      help='The hostname you want to connect to')
    parser.add_option('-P', '--port', action='store', type='int', dest='port', default=9990,
                      help='The port JBoss management console is runnung on')
    parser.add_option('-u', '--user', action='store', type='string', dest='user', default=None,
                      help='The username you want to login as')
    parser.add_option('-p', '--pass', action='store', type='string', dest='passwd', default=None,
                      help='The password you want to use for that user')
    parser.add_option('-M', '--mode', action="store", type='choice', dest='mode', default='standalone',
                      help='The mode the server is running', choices=['standalone', 'domain'])
    parser.add_option('-n', '--node', action='store', type='string', dest='node', default=None,
                      help='The wildfly node (host) this server is running (domain mode)')
    parser.add_option('-i', '--instance', action='store', type='string', dest='instance', default=None,
                      help='The wildfly instance (server-config) to check (domain mode)')
    parser.add_option('-W', '--warning', action='store', dest='warning', default=None,
                      help='The warning threshold we want to set')
    parser.add_option('-C', '--critical', action='store', dest='critical', default=None,
                      help='The critical threshold we want to set')
    parser.add_option('-A', '--action', action='store', type='choice', dest='action', default='server_status',
                      help='The action you want to take', choices=ACTIONS)
    parser.add_option('-D', '--perf-data', action='store_true', dest='perf_data', default=False,
                      help='Enable output of Nagios performance data')
    parser.add_option('-m', '--memorypool', action='store', dest='memory_pool', default=None,
                      help='The memory pool type')
    parser.add_option('-q', '--queuename', action='store', dest='queue_name', default=None,
                      help='The queue name for which you want to retrieve queue depth')
    parser.add_option('-d', '--datasource', action='store', dest='datasource_name', default=None,
                      help='The datasource name for which you want to retrieve statistics')
    parser.add_option('-s', '--poolstats', action='store', dest='ds_stat_type', default=None,
                      help='The datasource pool statistics type')
    parser.add_option('-t', '--threadstats', action='store', dest='thread_stat_type', default=None,
                      help='The threading statistics type', choices=THREAD_STAT_TYPES)

    options, arguments = parser.parse_args()
    CONFIG['host'] = options.host
    CONFIG['port'] = options.port
    CONFIG['user'] = options.user
    CONFIG['password'] = options.passwd
    CONFIG['instance'] = options.instance
    CONFIG['node'] = options.node
    CONFIG['mode'] = options.mode

    args = dict()

    if options.action not in ['server_status', 'deployment_status']:
        args['perf_data'] = options.perf_data

    if options.action == 'server_status':
        args['warning'] = str(options.warning or "")
        args['critical'] = str(options.critical or "")
    else:
        args['warning'] = float(options.warning or 0)
        args['critical'] = float(options.critical or 0)

    actions = {
        'server_status': lambda arg: check_server_status(**arg),
        'deployment_status': lambda arg: check_deployment_status(**arg),
        'gc_time': lambda arg: check_gctime(memory_pool=options.memory_pool, **arg),
        'queue_depth': lambda arg: check_queue_depth(queue_name=options.queue_name, **arg),
        'heap_usage': lambda arg: check_heap_usage(**arg),
        'non_heap_usage': lambda arg: check_non_heap_usage(**arg),
        'eden_space_usage': lambda arg: check_eden_space_usage(memory_pool=options.memory_pool, **arg),
        'olg_gen_usage': lambda arg: check_old_gen_usage(memory_pool=options.memory_pool, **arg),
        'perm_gen_usage': lambda arg: check_old_gen_usage(memory_pool=options.memory_pool, **arg),
        'code_cache_usage': lambda arg: check_code_cache_usage(memory_pool=options.memory_pool, **arg),
        'datasource': lambda arg: check_non_xa_datasource(
            ds_name=options.datasource_name, ds_stat_type=options.ds_stat_type, **arg),
        'xa_datasource': lambda arg: check_xa_datasource(
            ds_name=options.datasource_name, ds_stat_type=options.ds_stat_type, **arg),
        'threading': lambda arg: check_threading(
            thread_stat_type=options.thread_stat_type, **arg),
    }

    if options.action in actions:
        return actions[options.action](args)

    return 2


def _is_domain():
    return CONFIG['mode'] == 'domain'


def _exit_with_general_warning(exc):
    """
    :param exc: exception
    """
    if isinstance(exc, SystemExit):
        return exc

    print("WARNING - General JbossAS warning:", exc)
    return 1


def _exit_with_general_critical(exc):
    if isinstance(exc, SystemExit):
        return exc

    print("CRITICAL - General JbossAS Error:", exc)
    return 2


def _print_status(status, message, perf_data=None):
    if perf_data:
        print("{0} - {1} | {2}".format(NAGIOS_STATUS[status], message, perf_data))
    else:
        print("{0} - {1}".format(NAGIOS_STATUS[status], message))


def check_deployment_status(warning=None, critical=None):
    critical = critical or "FAILED"
    warning = warning or ["STOPPED"]
    ok = ["OK", "RUNNING"]

    url = '/deployment/*'
    payload = {'operation': 'attribute', 'name': 'status'}
    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    res = _get_digest_auth_json(url, payload)

    deployments = dict()
    return_code = 0
    for result in res:
        deployment = next(iter(result.get('address') or []), {}).get('deployment')
        status = result.get('result')
        deployments[deployment] = status
        deployment_status = _check_levels(status, warning, critical, ok)
        return_code = max([return_code, deployment_status])

    _print_status(return_code, '%d Deployments checked' % len(deployments))
    for deployment, status in deployments.items():
        print("%s is %s" % (deployment, status))

    return return_code


def check_server_status(ok=None, warning=None, critical=None):
    ok = ok or ["running"]
    warning = warning or ["restart-required", "reload-required"]
    critical = critical or ["stopped"]

    url = ''
    payload = {'operation': 'attribute', 'name': 'server-state'}
    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    response = _get_digest_auth_json(url, payload)

    message = "Server Status '{0}'".format(response)
    status = _check_levels(response, warning, critical, ok)
    _print_status(status, message)
    return status


def get_memory_usage():
    payload = {'include-runtime': 'true'}
    url = "/core-service/platform-mbean/type/memory"

    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    data = _get_digest_auth_json(url, payload)
    memory_types = ['heap-memory-usage', 'non-heap-memory-usage']
    fields = ['init', 'used', 'committed', 'max']

    for memory_type in memory_types:
        for field in fields:
            # convert to megabyte
            data[memory_type][field] /= (1024 * 1024)

    return data


def check_heap_usage(warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90

    memory = get_memory_usage()['heap-memory-usage']
    used_heap = memory['used']
    max_heap = memory['max']
    percent = round((float(used_heap * 100) / max_heap), 2)

    message = "Heap Memory Utilization %.2f MB of %.2f MB" % (used_heap, max_heap)
    perf_data = _performance_data(perf_data, [("%dMB" % used_heap, "heap_usage",
                                               max_heap * warning / 100,
                                               max_heap * critical / 100,
                                               memory['init'],
                                               max_heap)])

    status = _check_levels(percent, warning, critical)
    _print_status(status, message, perf_data)
    return status


def check_non_heap_usage(warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90

    memory = get_memory_usage()['non-heap-memory-usage']
    used_heap = memory['used']
    max_heap = memory['max']
    percent = round((float(used_heap * 100) / max_heap), 2)

    message = "Non Heap Memory Utilization %.2f MB of %.2f MB" % (used_heap, max_heap)
    perf_data = _performance_data(perf_data, [("%dMB" % used_heap, "non_heap_usage",
                                               max_heap * warning / 100,
                                               max_heap * critical / 100,
                                               memory['init'],
                                               max_heap)])

    status = _check_levels(percent, warning, critical)
    _print_status(status, message, perf_data)
    return status


def get_memory_pool_usage(pool_name, memory_value):
    payload = {'include-runtime': 'true', 'recursive': 'true'}
    url = "/core-service/platform-mbean/type/memory-pool"

    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    data = _get_digest_auth_json(url, payload)
    usage = data['name'][pool_name]['usage'][memory_value] / (1024 * 1024)

    return usage


def check_eden_space_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90

    used_heap = get_memory_pool_usage(memory_pool, 'used')
    max_heap = get_memory_pool_usage(memory_pool, 'max')
    percent = round((float(used_heap * 100) / max_heap), 2)

    message = "Eden_Space Utilization %sMB of %sMB" % (used_heap, max_heap)
    perf_data = _performance_data(perf_data, [("%.2f%%" % percent, "eden_space_usage", warning, critical)])

    status = _check_levels(percent, warning, critical)
    _print_status(status, message, perf_data)
    return status


def check_old_gen_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90

    used_heap = get_memory_pool_usage(memory_pool, 'used')
    max_heap = get_memory_pool_usage(memory_pool, 'max')
    percent = round((float(used_heap * 100) / max_heap), 2)

    message = "Old_Gen Utilization %sMB of %sMB" % (used_heap, max_heap)
    perf_data = _performance_data(perf_data, [("%.2f%%" % percent, "old_gen_usage", warning, critical)])

    status = _check_levels(percent, warning, critical)
    _print_status(status, message, perf_data)
    return status


def check_perm_gen_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 90
    critical = critical or 95

    used_heap = get_memory_pool_usage(memory_pool, 'used')
    max_heap = get_memory_pool_usage(memory_pool, 'max')
    percent = round((float(used_heap * 100) / max_heap), 2)

    message = "Perm_Gen Utilization %sMB of %sMB" % (used_heap, max_heap)
    perf_data = _performance_data(perf_data, [("%.2f%%" % percent, "perm_gen_usage", warning, critical)])

    status = _check_levels(percent, warning, critical)
    _print_status(status, message, perf_data)
    return status


def check_code_cache_usage(memory_pool, warning, critical, perf_data):
    warning = warning or 90
    critical = critical or 95

    if memory_pool is None:
        memory_pool = 'Code_Cache'

    used_heap = get_memory_pool_usage(memory_pool, 'used')
    max_heap = get_memory_pool_usage(memory_pool, 'max')
    percent = round((float(used_heap * 100) / max_heap), 2)

    message = "Code_Cache Utilization %.2f MB of %.2f MB" % (used_heap, max_heap)
    perf_data = _performance_data(perf_data, [("%.2f%%" % percent, "code_cache_usage", warning, critical)])

    status = _check_levels(percent, warning, critical)
    _print_status(status, message, perf_data)
    return status


def check_gctime(memory_pool, warning, critical, perf_data):
    # Make sure you configure right values for your application
    warning = warning or 500
    critical = critical or 1000

    payload = {'include-runtime': 'true', 'recursive': 'true'}
    url = "/core-service/platform-mbean/type/garbage-collector"

    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    res = _get_digest_auth_json(url, payload)

    gc_time = res['name'][memory_pool]['collection-time']
    gc_count = res['name'][memory_pool]['collection-count']

    avg_gc_time = 0

    if gc_count > 0:
        avg_gc_time = float(gc_time / gc_count)

    message = "GC '%s' total-time=%dms count=%s avg-time=%.2fms" % (memory_pool, gc_time, gc_count, avg_gc_time)
    perf_data = _performance_data(perf_data, [("%.2fms" % avg_gc_time, "gctime", warning, critical)])

    status = _check_levels(avg_gc_time, warning, critical, message)
    _print_status(status, message, perf_data)
    return status


def check_threading(thread_stat_type, warning, critical, perf_data):
    warning = warning or 100
    critical = critical or 200

    payload = {'include-runtime': 'true'}
    url = "/core-service/platform-mbean/type/threading"

    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    data = _get_digest_auth_json(url, payload)
    data = data[thread_stat_type]

    message = "Threading Statistics '%s':%s " % (thread_stat_type, data)
    perf_data = _performance_data(perf_data, [(data, "threading", warning, critical)])

    status = _check_levels(data, warning, critical)
    _print_status(status, message, perf_data)
    return status


def check_queue_depth(queue_name, warning, critical, perf_data):
    warning = warning or 100
    critical = critical or 200

    if queue_name is None:
        return _exit_with_general_critical("The queue name '%s' is not valid" % queue_name)

    payload = {'include-runtime': 'true', 'recursive': 'true'}
    url = "/subsystem/messaging/hornetq-server/default/jms-queue/" + queue_name

    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    data = _get_digest_auth_json(url, payload)
    queue_depth = data['message-count']

    message = "Queue %s depth %s" % (queue_name, queue_depth)
    perf_data = _performance_data(perf_data, [(queue_depth, "queue_depth", warning, critical)])

    status = _check_levels(queue_depth, warning, critical)
    _print_status(status, message, perf_data)
    return status


def get_datasource_stats(is_xa, ds_name, ds_stat_type):
    if ds_name is None:
        return _exit_with_general_critical("The ds_name name '%s' is not valid" % ds_name)
    if ds_stat_type not in DS_STAT_TYPES:
        return _exit_with_general_critical("The datasource statistics type of '%s' is not valid" % ds_stat_type)

    payload = {'include-runtime': 'true', 'recursive': 'true'}
    if is_xa:
        url = "/subsystem/datasources/xa-data-source/" + ds_name + "/statistics/pool/"
    else:
        url = "/subsystem/datasources/data-source/" + ds_name + "/statistics/pool/"

    if _is_domain():
        url = '/host/{}/server/{}'.format(CONFIG['node'], CONFIG['instance']) + url

    data = _get_digest_auth_json(url, payload)
    data = data[ds_stat_type]

    return data


def check_non_xa_datasource(ds_name, ds_stat_type, warning, critical, perf_data):
    warning = warning or 0
    critical = critical or 10

    data = get_datasource_stats(False, ds_name, ds_stat_type)

    message = "DataSource %s %s" % (ds_stat_type, data)
    perf_data = _performance_data(perf_data, [(data, "datasource", warning, critical)])
    status = _check_levels(data, warning, critical)
    _print_status(status, message, perf_data)
    return status


def check_xa_datasource(ds_name, ds_stat_type, warning, critical, perf_data):
    warning = warning or 0
    critical = critical or 10

    data = get_datasource_stats(True, ds_name, ds_stat_type)

    message = "XA DataSource %s %s" % (ds_stat_type, data)
    perf_data = _performance_data(perf_data, [(data, "xa_datasource", warning, critical)])
    status = _check_levels(data, warning, critical, message)
    _print_status(status, message, perf_data)
    return status


#
# main app
#
if __name__ == "__main__":
    sys.exit(main())
