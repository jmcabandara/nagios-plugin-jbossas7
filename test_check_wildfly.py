import check_wildfly as wf
import requests_mock
import pytest

BASE_URL = 'http://localhost:9990/management'


def before():
    wf.CONFIG['mode'] = 'standalone'


@pytest.fixture()
def requests():
    mocker = requests_mock.Mocker()
    mocker.start()
    yield mocker
    mocker.stop()


def test_check_status_ok(requests):
    requests.get(BASE_URL + '?operation=read-attribute&name=server-state',
                 text='{"result":"running"}')
    result = wf.check_server_status()
    assert result == 0


def test_check_status_warning_on_restart(requests):
    requests.get(BASE_URL + '?operation=read-attribute&name=server-state',
                 text='{"result":"restart-required"}')
    result = wf.check_server_status()
    assert result == 1


def test_check_status_warning_on_reload_required(requests):
    requests.get(BASE_URL + '?operation=read-attribute&name=server-state',
                 text='{"result":"reload-required"}')
    result = wf.check_server_status()
    assert result == 1


def test_check_status_critical(requests):
    requests.get(BASE_URL + '?operation=read-attribute&name=server-state',
                 text='{"result":"stopped"}')
    result = wf.check_server_status()
    assert result == 2


def test_performance_data(requests, capsys):
    requests.get(BASE_URL + '?operation=read-attribute&name=server-state',
                 text='{"result":"running"}')
    wf.check_server_status(perf_data=True)
    out, err = capsys.readouterr()
    assert '|server_status=running;' in str(out)


def test_check_status_with_domain(requests):
    wf.CONFIG['mode'] = 'domain'
    wf.CONFIG['node'] = 'master'
    wf.CONFIG['instance'] = 'server-one'
    requests.get(BASE_URL + '/host/master/server/server-one?operation=read-attribute&name=server-state',
                 text='{"result":"running"}')
    result = wf.check_server_status()
    assert result == 0
