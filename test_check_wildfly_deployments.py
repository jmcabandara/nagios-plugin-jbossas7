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


STATUS = [
    {"address": [{"deployment": "deployment-one.war"}], "outcome": "success", "result": "OK"},
    {"address": [{"deployment": "deployment-two.ear"}], "outcome": "success", "result": "OK"},
    {"address": [{"deployment": "depoyment-three.jar"}], "outcome": "success", "result": "OK"}]


def test_check_deployments_ok(requests):
    requests.get(BASE_URL + '/deployment/*', text=json.dumps(STATUS))
    result = wf.check_deployment_status()
    assert result == 0


def test_check_deployments_warning(requests):
    failed = list(STATUS)
    failed[0]['result'] = "STOPPED"
    requests.get(BASE_URL + '/deployment/*', text=json.dumps(STATUS))
    result = wf.check_deployment_status()
    assert result == 1


def test_check_deployments_critical(requests):
    failed = list(STATUS)
    failed[0]['result'] = "FAILED"
    requests.get(BASE_URL + '/deployment/*', text=json.dumps(STATUS))
    result = wf.check_deployment_status()
    assert result == 2


def test_check_deployments_unknown(requests):
    requests.get(BASE_URL + '/deployment/*', status_code=404)
    with pytest.raises(SystemExit) as exit_info:
        wf.check_deployment_status()
    assert exit_info.value.code == -1
