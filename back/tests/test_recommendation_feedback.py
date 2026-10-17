from app.data.seed import DEMO_USERNAME, DEMO_PASSWORD
from app.services import scoring_service, weather_service


def auth(client, username=DEMO_USERNAME, password=DEMO_PASSWORD):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_dislike_excludes_both_recommendation_paths_and_can_be_revoked(client):
    headers = auth(client)
    first = client.post('/api/ai/chat', headers=headers, json={'message': '推荐一道菜', 'use_ai': False, 'cook_minutes': 240}).json()
    target = first['recipes'][0]['id']
    feedback = client.put(f'/api/ai/feedback/{target}', headers=headers, json={'value': 'dislike', 'reason': '太费时'})
    assert feedback.status_code == 200
    for path, body, key in [('/api/ai/chat', {'message': '推荐三道菜', 'use_ai': False}, 'recipes'),
                            ('/api/ai/recommend', {'count': 3}, 'recommendations')]:
        result = client.post(path, headers=headers, json={**body, 'cook_minutes': 240}).json()
        recipes = result[key] if key == 'recipes' else [p['recipe'] for p in result[key]]
        assert target not in [r['id'] for r in recipes]
    assert client.get('/api/ai/feedback', headers=headers).json()[0]['reason'] == '太费时'
    assert client.put(f'/api/ai/feedback/{target}', headers=headers, json={'value': 'neutral'}).status_code == 200
    assert client.get('/api/ai/feedback', headers=headers).json() == []


def test_likes_only_adjust_safe_candidate_scores_and_are_account_scoped(client, session):
    headers = auth(client)
    weather = weather_service.current_weather(month=10)
    options = dict(month=10, weather=weather, constraints=scoring_service.HardConstraints(cook_minutes=240), candidate_ids=[1, 2, 3, 4], limit=24)
    before = {c.item_id: c.quality for c in scoring_service.score_dishes(session, user_id=1, **options)}
    target = next(iter(before))
    assert client.put(f'/api/ai/feedback/{target}', headers=headers, json={'value': 'like'}).status_code == 200
    from app.models.user import User
    from sqlmodel import select
    user = session.exec(select(User).where(User.username == DEMO_USERNAME)).one()
    after = scoring_service.score_dishes(session, user_id=user.id, **options)
    assert next(c.quality for c in after if c.item_id == target) == before[target] + 0.6
    forbidden = scoring_service.score_dishes(session, user_id=user.id, **{**options, 'exclude_ids': {target}})
    assert target not in [c.item_id for c in forbidden]
    client.post('/api/auth/register', json={'username': 'feedback-other', 'password': '12345678'})
    other = auth(client, 'feedback-other', '12345678')
    assert client.get('/api/ai/feedback', headers=other).json() == []
    assert client.put('/api/ai/feedback/999999', headers=headers, json={'value': 'like'}).status_code == 404
    assert client.get('/api/ai/feedback').status_code == 401


def test_batch_inventory_is_idempotent_and_invalid_batch_is_atomic(client):
    headers = auth(client)
    client.post('/api/my-foods', headers=headers, json={'food_id': 1, 'amount': 200, 'unit': '克'})
    batch = client.post('/api/my-foods/batch', headers=headers, json={'food_ids': [1, 2, 2]})
    assert batch.status_code == 200, batch.text
    assert batch.json() == {'added_count': 1, 'existing_count': 1}
    assert client.post('/api/my-foods/batch', headers=headers, json={'food_ids': [1, 2]}).json()['added_count'] == 0
    before = client.get('/api/my-foods', headers=headers).json()
    assert next(i for i in before if i['food_id'] == 1)['amount'] == 200
    assert client.post('/api/my-foods/batch', headers=headers, json={'food_ids': [3, 999999]}).status_code == 404
    assert client.get('/api/my-foods', headers=headers).json() == before
    assert client.post('/api/my-foods/batch', json={'food_ids': [1]}).status_code == 401
