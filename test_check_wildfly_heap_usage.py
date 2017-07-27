import copy

import check_wildfly as wf
import requests_mock
import pytest
import json

BASE_URL = 'http://localhost:9990/management'


def before():
    wf.CONFIG['mode'] = 'standalone'


@pytest.fixture()
def requests():
    mocker = requests_mock.Mocker()
    mocker.start()
    yield mocker
    mocker.stop()


HEAP_USAGE = {'heap-memory-usage': {'init': 268435456, 'used': 439564992, 'committed': 587726848, 'max': 1037959168},
              'non-heap-memory-usage': {'init': 2555904, 'used': 217580768, 'committed': 236462080, 'max': 536870912},
              'object-name': 'java.lang:type=Memory', 'object-pending-finalization-count': 0, 'verbose': False}


def test_check_heap_usage(requests):
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(HEAP_USAGE))
    result = wf.check_heap_usage(80, 90, False)
    assert result == 0


def test_check_heap_usage_warning(requests):
    memory_usage = copy.deepcopy(HEAP_USAGE)
    memory_usage['heap-memory-usage']['used'] = 882265292
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(memory_usage))
    result = wf.check_heap_usage(80, 90, False)
    assert result == 1


def test_check_heap_usage_critical(requests):
    memory_usage = copy.deepcopy(HEAP_USAGE)
    memory_usage['heap-memory-usage']['used'] = 986061209
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(memory_usage))
    result = wf.check_heap_usage(80, 90, False)
    assert result == 2


def test_check_heap_usage_performance_data(requests, capsys):
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(HEAP_USAGE))
    result = wf.check_heap_usage(80, 90, True)
    out, err = capsys.readouterr()
    assert '| heap_usage=419MB;791.9;890.8875;256.0;989.875' in out
    assert result == 0


def test_check_heap_usage_unknown(requests):
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', status_code=404)
    with pytest.raises(SystemExit) as exit_info:
        wf.check_heap_usage(80, 90, False)
    assert exit_info.value.code == -1


def test_check_non_heap_usage(requests):
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(HEAP_USAGE))
    result = wf.check_heap_usage(80, 90, False)
    assert result == 0


def test_check_non_heap_usage_with_unlimited_heap(requests):
    memory_usage = copy.deepcopy(HEAP_USAGE)
    memory_usage['non-heap-memory-usage']['max'] = -1
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(HEAP_USAGE))
    result = wf.check_heap_usage(80, 90, False)
    assert result == 0


def test_check_non_heap_usage_warning(requests):
    memory_usage = copy.deepcopy(HEAP_USAGE)
    memory_usage['non-heap-memory-usage']['used'] = 456340275
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(memory_usage))
    result = wf.check_non_heap_usage(80, 90, False)
    assert result == 1


def test_check_non_heap_usage_critical(requests):
    memory_usage = copy.deepcopy(HEAP_USAGE)
    memory_usage['non-heap-memory-usage']['used'] = 510027366
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(memory_usage))
    result = wf.check_non_heap_usage(80, 90, False)
    assert result == 2


def test_check_non_heap_usage_performance_data(requests, capsys):
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', text=json.dumps(HEAP_USAGE))
    result = wf.check_non_heap_usage(80, 90, True)
    out, err = capsys.readouterr()
    print(out)
    assert '| non_heap_usage=207MB;409.6;460.8;2.4375;512.0' in out
    assert result == 0


def test_check_non_heap_usage_unknown(requests):
    requests.get(BASE_URL + '/core-service/platform-mbean/type/memory', status_code=404)
    with pytest.raises(SystemExit) as exit_info:
        wf.check_non_heap_usage(80, 90, False)
    assert exit_info.value.code == -1
