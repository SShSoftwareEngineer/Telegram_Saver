"""
Tests of the request guard: Host, Origin and Sec-Fetch-Site checks.
Тесты защиты запросов: проверки Host, Origin и Sec-Fetch-Site.
"""

import logging
import pytest
from fastapi.testclient import TestClient
from configs.config import FormCfg

GOOD_ORIGINS = ['http://127.0.0.1:5000', 'http://localhost:5000']


@pytest.mark.parametrize('origin', GOOD_ORIGINS)
def test_post_with_own_origin_passes(client: TestClient, origin: str):
    """The page of the server itself (any of its two addresses) can post / Своя страница может отправлять POST"""
    response = client.post('/db_tag_all_sorting', headers={'Origin': origin})
    assert response.status_code != 403


def test_post_without_origin_passes(client: TestClient):
    """curl and scripts send no Origin and are accepted / curl и скрипты без Origin принимаются"""
    assert client.post('/db_tag_all_sorting').status_code != 403


@pytest.mark.parametrize('origin', ['https://evil.example', 'http://127.0.0.1:8000', 'http://localhost', 'null'])
def test_post_with_foreign_origin_is_rejected(client: TestClient, origin: str):
    """A foreign origin (another site, port or scheme, or `null`) is rejected with JSON / Чужой Origin отклоняется"""
    response = client.post('/db_tag_all_sorting', headers={'Origin': origin})
    assert response.status_code == 403
    assert response.json() == {'error': 'Forbidden'}


def test_rejected_post_does_nothing(client: TestClient, db_handler):
    """The route is not reached: the state stays as it was / До роута дело не доходит: состояние не меняется"""
    form = {FormCfg.db_detail_tags['tag_sorting_field']: '1'}
    before = db_handler.current_state.all_tags_list_sorting
    client.post('/db_tag_all_sorting', headers={'Origin': 'https://evil.example'}, data=form)
    assert db_handler.current_state.all_tags_list_sorting == before
    # The same request from the own page changes it, so the check above proves something
    # Тот же запрос со своей страницы меняет его, поэтому проверка выше что-то доказывает
    client.post('/db_tag_all_sorting', headers={'Origin': GOOD_ORIGINS[0]}, data=form)
    assert db_handler.current_state.all_tags_list_sorting != before


@pytest.mark.parametrize('host', ['evil.example', 'evil.example:5000', '127.0.0.1', '127.0.0.1:8000', 'localhost:80'])
def test_foreign_host_is_rejected(client: TestClient, host: str):
    """DNS rebinding: any Host other than the server address is rejected, even for GET / Чужой Host отклоняется"""
    response = client.get('/status_output', headers={'Host': host})
    assert response.status_code == 403


@pytest.mark.parametrize('host', ['127.0.0.1:5000', 'localhost:5000'])
def test_own_hosts_pass(client: TestClient, host: str):
    """Both addresses of the server work / Оба адреса сервера работают"""
    assert client.get('/status_output', headers={'Host': host}).status_code == 200


@pytest.mark.parametrize('method', ['get', 'post'])
def test_cross_site_request_is_rejected(client: TestClient, method: str):
    """A foreign site is rejected for GET (`<img src>`) as well as POST / Чужой сайт отклоняется и на GET, и на POST"""
    response = getattr(client, method)('/status_output', headers={'Sec-Fetch-Site': 'cross-site'})
    assert response.status_code == 403


def test_cross_site_main_page_opens(client: TestClient):
    """A link from another site opens the main page / Ссылка с другого сайта открывает главную страницу"""
    response = client.get('/', headers={'Sec-Fetch-Site': 'cross-site'})
    assert response.status_code == 200


@pytest.mark.parametrize('value', ['same-origin', 'same-site', 'none'])
def test_other_fetch_sites_pass(client: TestClient, value: str):
    """The own page (and a typed address) is accepted / Своя страница (и набранный адрес) принимается"""
    assert client.get('/status_output', headers={'Sec-Fetch-Site': value}).status_code == 200


def test_rejection_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture):
    """The reason of a rejection goes to the log / Причина отказа попадает в лог"""
    with caplog.at_level(logging.WARNING, logger='web.middleware'):
        client.post('/db_tag_all_sorting', headers={'Origin': 'https://evil.example'})
    assert 'foreign Origin' in caplog.text
    assert '/db_tag_all_sorting' in caplog.text
