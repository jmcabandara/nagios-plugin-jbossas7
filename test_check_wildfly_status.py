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
    requests.post(BASE_URL,
                  text='{"result":"running"}')
    result = wf.check_server_status()
    assert result == 0


def test_check_status_warning_on_restart(requests):
    requests.post(BASE_URL,
                  text='{"result":"restart-required"}')
    result = wf.check_server_status()
    assert result == 1


def test_check_status_warning_on_reload_required(requests):
    requests.post(BASE_URL,
                  text='{"result":"reload-required"}')
    result = wf.check_server_status()
    assert result == 1


def test_check_status_critical(requests):
    requests.post(BASE_URL,
                  text='{"result":"stopped"}')
    result = wf.check_server_status()
    assert result == 2


def test_check_status_with_domain(requests):
    wf.CONFIG['mode'] = 'domain'
    wf.CONFIG['node'] = 'master'
    wf.CONFIG['instance'] = 'server-one'
    requests.post(BASE_URL + '/host/master/server/server-one',
                  text='{"result":"running"}')
    result = wf.check_server_status()
    assert result == 0