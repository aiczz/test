from app.core.config import settings
from app.models.recipe import Recipe
from app.services import scoring_service
from app.services.scoring_service import HardConstraints
from app.services.weather_service import current_weather


def test_no_image_recipe_excluded_before_recommendation(session, monkeypatch):
    recipe = session.get(Recipe, 1)
    recipe.image_url = None
    session.add(recipe)
    session.commit()
    monkeypatch.setattr(scoring_service, 'has_image', lambda name: False)
    args = dict(month=10, weather=current_weather(month=10),
                constraints=HardConstraints(cook_minutes=240), candidate_ids=[1])
    settings.recipe_images_only = False
    assert scoring_service.score_dishes(session, **args)
    settings.recipe_images_only = True
    assert scoring_service.score_dishes(session, **args) == []
    monkeypatch.setattr(scoring_service, 'has_image', lambda name: True)
    assert scoring_service.score_dishes(session, **args)
