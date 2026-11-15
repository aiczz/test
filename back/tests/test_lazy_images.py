import base64
import time
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.models.food import Food
from app.models.image_cache import ImageBudget, ImageCache
from app.services import image_service as images

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=')


@pytest.fixture
def photo_setup(monkeypatch, tmp_path, session):
    for name, value in dict(image_generation_enabled=True, image_generation_url='https://provider.invalid/images',
                            image_api_key='fake-key', image_model='fake-model', image_daily_limit=40,
                            image_storage_dir=str(tmp_path / 'generated'),
                            image_asset_dir=str(tmp_path / 'assets')).items():
        monkeypatch.setattr(settings, name, value)
    (tmp_path / 'assets').mkdir()
    jobs = []
    monkeypatch.setattr(images._workers, 'submit', lambda *args: jobs.append(args))
    session.add(Food(name='待配图食材', category='vegetable'))
    session.commit()
    yield jobs
    # Release slots for captured jobs that a particular test did not execute.
    for job in jobs:
        images._slots.release()


def finish(jobs):
    job = jobs.pop(0)
    job[0](*job[1:])


def test_bundled_photo_alias_and_content(client, session, photo_setup):
    _, _, filename = images.identity('food', '番茄')
    (Path(settings.image_asset_dir) / filename).write_bytes(PNG)
    a = client.post('/api/images/resolve', json={'kind': 'food', 'name': '番茄'}).json()
    b = client.post('/api/images/resolve', json={'kind': 'food', 'name': '西红柿'}).json()
    assert a['status'] == 'ready' and a['source'] == 'bundled'
    assert a['key'] == b['key']
    response = client.get(a['url'])
    assert response.content == PNG and 'max-age' in response.headers['cache-control']
    assert not photo_setup


def test_no_key_no_generation(session, photo_setup, monkeypatch):
    monkeypatch.setattr(settings, 'image_api_key', '')
    r = images.resolve(session, 'food', '待配图食材', allow_generation=True)
    assert r['status'] == 'disabled' and not photo_setup


def test_anonymous_and_unknown_cannot_generate(session, photo_setup):
    assert images.resolve(session, 'food', '待配图食材', allow_generation=False)['status'] == 'login_required'
    assert images.resolve(session, 'food', '随意生成的文字', allow_generation=True)['status'] == 'unknown'
    assert not photo_setup


def test_duplicate_requests_share_job_and_persisted_file(session, photo_setup, monkeypatch):
    monkeypatch.setattr(images, '_provider', lambda prompt: (PNG, 'png'))
    first = images.resolve(session, 'food', '待配图食材', allow_generation=True)
    second = images.resolve(session, 'food', '待配图食材', allow_generation=True)
    assert first['key'] == second['key'] and len(photo_setup) == 1
    finish(photo_setup)
    # Fresh session simulates subsequent access after in-memory caches are gone.
    with Session(session.get_bind()) as fresh:
        ready = images.resolve(fresh, 'food', '待配图食材', allow_generation=False)
        assert ready['status'] == 'ready'
        assert images.photo_path(fresh.get(ImageCache, ready['key'])).read_bytes() == PNG


def test_failure_cooldown_and_max_attempts(session, photo_setup, monkeypatch):
    def fail(_):
        raise RuntimeError('sensitive-provider-error')
    monkeypatch.setattr(images, '_provider', fail)
    r = images.resolve(session, 'food', '待配图食材', allow_generation=True)
    finish(photo_setup)
    session.expire_all()
    row = session.get(ImageCache, r['key'])
    assert row.status == 'failed' and row.retry_at > time.time()
    assert 'sensitive' not in row.error
    images.resolve(session, 'food', '待配图食材', allow_generation=True)
    assert not photo_setup
    row.retry_at, row.attempts = 0, settings.image_max_attempts
    session.add(row)
    session.commit()
    assert not images.resolve(session, 'food', row.name, allow_generation=True)['can_retry']


def test_daily_budget_prevents_cost(session, photo_setup, monkeypatch):
    monkeypatch.setattr(settings, 'image_daily_limit', 0)
    assert images.resolve(session, 'food', '待配图食材', allow_generation=True)['status'] == 'limited'
    assert not photo_setup
    assert session.exec(select(ImageBudget)).first().used == 0


def test_stale_job_can_resume(session, photo_setup):
    key, name, _ = images.identity('food', '待配图食材')
    session.add(ImageCache(key=key, name=name, kind='food', status='generating', updated_at=1))
    session.commit()
    assert images.resolve(session, 'food', name, allow_generation=True)['status'] == 'generating'
    assert len(photo_setup) == 1


def test_deleted_cached_file_is_not_reported_ready(session, photo_setup):
    key, name, _ = images.identity('food', '待配图食材')
    session.add(ImageCache(key=key, name=name, kind='food', status='ready', filename='deleted.png'))
    session.commit()
    r = images.resolve(session, 'food', name, allow_generation=True)
    assert r['status'] == 'generating' and r['url'] is None
    assert len(photo_setup) == 1


def test_provider_base64_and_reject_untrusted_download(monkeypatch, photo_setup):
    real_client = httpx.Client
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(PNG).decode()}]})
    monkeypatch.setattr(images.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    assert images._provider('example') == (PNG, 'png')
    assert len(requests) == 1
    def malicious(request):
        return httpx.Response(200, json={'data': [{'url': 'http://127.0.0.1/secret'}]})
    monkeypatch.setattr(images.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(malicious), **kw))
    with pytest.raises(ValueError, match='not permitted'):
        images._provider('example')


def test_route_rejects_invalid_kind_and_missing_file(client, photo_setup):
    assert client.post('/api/images/resolve', json={'kind': 'avatar', 'name': 'x'}).status_code == 422
    assert client.get('/api/images/not-a-key/content').status_code == 404
