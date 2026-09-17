"""种子数据（说明书 §26）。

幂等：重复执行不会重复插入，可以放心在每次启动时调用。

内容来自前端现有的假数据（`front/mealmind/lib/data/mock.dart`），
这样前端从 mock 切到真接口时，界面上看到的东西是一致的 ——
不会出现「接了后端反而内容全变了」的尴尬。

演示账号：答辩时评委不用注册就能进去。
"""

from sqlmodel import Session, select

from app.core.database import engine
from app.core.security import hash_password
from app.models.food import Food, FoodSeason
from app.models.recipe import Recipe, RecipeIngredient, RecipeStep
from app.models.user import User, UserPreference

# =====================================================================
# 演示账号
# =====================================================================

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "shishi2026"
DEMO_NICKNAME = "演示用户"
DEMO_FAMILY_SIZE = 3

# 管理员账号：能封禁其他账号、看用户统计和登录记录。
# ⚠️ 这是【演示用】密码，已写进 back/README.md。真实部署前必须改掉，
#    或者用 .env 覆盖（见 README 第七节）。
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123456"

# =====================================================================
# 食材
#
# ⚠️ 前端的图片是打包进 App 的本地 asset，所以 image_url 直接存前端的
#    asset 路径 —— 前端拿到就能直接用，不必再从后端拉一遍图。
#    将来图片改由后端托管（说明书 §27），只改这一列的值即可。
# =====================================================================

_FOODS: list[dict] = [
    {
        "name": "莲藕",
        "category": "vegetable",
        "image_url": "assets/images/lotus-clean.jpg",
        "description": "秋天上市的时令根茎，润燥养胃、脆嫩清甜。",
        "nutrition_summary": "润燥养胃、秋季适宜",
        "texture": "脆嫩",
        "common_methods": "炖汤 / 清炒 / 凉拌",
        "tags": ["润燥养胃", "秋季适宜"],
        "season": ("秋季", 9, 11, 95),
    },
    {
        "name": "南瓜",
        "category": "vegetable",
        "image_url": "assets/images/pumpkin-clean.jpg",
        "description": "软糯香甜，蒸煮烤都合适。",
        "nutrition_summary": "富含膳食纤维、软糯香甜",
        "texture": "软糯",
        "common_methods": "蒸 / 煮粥 / 烤",
        "tags": ["富含膳食纤维", "软糯香甜"],
        "season": ("秋季", 8, 11, 90),
    },
    {
        "name": "西红柿",
        "category": "vegetable",
        "image_url": "assets/images/tomato-clean.jpg",
        "description": "酸甜多汁，生吃熟做都行。",
        "nutrition_summary": "富含维生素C、酸甜开胃",
        "texture": "多汁",
        "common_methods": "炒蛋 / 煮汤 / 凉拌",
        "tags": ["富含维生素C", "酸甜开胃"],
        "season": ("夏季", 6, 9, 85),
    },
    {
        "name": "小白菜",
        "category": "vegetable",
        "image_url": "assets/images/bokchoy-clean.jpg",
        "description": "清爽鲜嫩，家常常备的绿叶菜。",
        "nutrition_summary": "清爽鲜嫩、家常常备",
        "texture": "鲜嫩",
        "common_methods": "清炒 / 煮汤",
        "tags": ["清爽鲜嫩", "家常常备"],
        "season": ("全年", 1, 12, 70),
    },
    {
        "name": "胡萝卜",
        "category": "vegetable",
        "image_url": "assets/images/carrot-clean.jpg",
        "description": "耐储存，配菜提色又提味。",
        "nutrition_summary": "富含胡萝卜素、增强免疫",
        "texture": "脆硬",
        "common_methods": "炖 / 炒 / 凉拌",
        "tags": ["富含胡萝卜素", "增强免疫"],
        "season": ("秋冬季", 9, 12, 80),
    },
    {
        "name": "鸡蛋",
        "category": "meat_egg",
        "image_url": "assets/images/egg-clean.jpg",
        "description": "最家常的优质蛋白来源。",
        "nutrition_summary": "优质蛋白、营养全面",
        "texture": "嫩滑",
        "common_methods": "炒 / 蒸 / 煮",
        "tags": ["优质蛋白", "营养全面"],
        "season": ("全年", 1, 12, 70),
    },
]

# =====================================================================
# 菜谱
#
# duration_minutes 是前端首页「按你的条件能做」用来筛「每日可用烹饪时间」
# 的字段，必须是真实的分钟数。
# 配料里的 category 用于购物清单分组。
# =====================================================================

_RECIPES: list[dict] = [
    {
        "name": "莲藕排骨汤",
        "image_url": "assets/images/hero-soup.jpg",
        "description": "清甜滋补，秋日暖汤",
        "duration_minutes": 60,
        "servings": 3,
        "difficulty": "简单",
        "category": "汤羹",
        "season_recommendation": "秋季",
        "tips": "小火慢炖 40 分钟，出锅前再放盐，肉更嫩。",
        "tags": ["秋日暖汤", "家常", "营养"],
        "ingredients": [
            ("莲藕", 1, "节", "蔬菜"),
            ("排骨", 500, "克", "肉蛋"),
            ("胡萝卜", 1, "根", "蔬菜"),
            ("姜", 3, "片", "调味"),
            ("葱", 2, "根", "调味"),
            ("盐", None, "适量", "调味"),
        ],
        "steps": [
            "排骨冷水下锅焯水，煮开后捞出冲洗干净。",
            "莲藕和胡萝卜去皮切块，姜切片，葱切段备用。",
            "所有食材放入锅中，加足量清水，大火煮开后转小火慢炖 40 分钟。",
            "出锅前加盐调味，撒上葱花即可。",
        ],
    },
    {
        "name": "番茄炒蛋",
        "image_url": "assets/images/tomato-egg.jpg",
        "description": "酸甜开胃，经典家常",
        "duration_minutes": 15,
        "servings": 3,
        "difficulty": "简单",
        "category": "家常菜",
        "season_recommendation": "夏季",
        "tips": "蛋液刚凝固就盛出，回锅再炒才不会老。",
        "tags": ["快手菜", "下饭"],
        "ingredients": [
            ("西红柿", 3, "个", "蔬菜"),
            ("鸡蛋", 4, "个", "肉蛋"),
            ("葱", 1, "根", "调味"),
            ("糖", 1, "小勺", "调味"),
            ("盐", None, "适量", "调味"),
        ],
        "steps": [
            "鸡蛋打散加少许盐搅匀，西红柿切块，葱切末。",
            "热锅倒油，倒入蛋液炒至刚凝固就盛出（别炒老）。",
            "锅中留底油，下西红柿炒出汁，加糖和盐调味。",
            "倒回炒好的鸡蛋翻炒均匀，撒葱花出锅。",
        ],
    },
    {
        "name": "清炒白菜",
        "image_url": "assets/images/cabbage.jpg",
        "description": "清爽脆嫩，简单快手",
        "duration_minutes": 10,
        "servings": 3,
        "difficulty": "简单",
        "category": "家常菜",
        "season_recommendation": "全年",
        "tips": "大火快炒，断生立刻出锅，久炒会出水变软。",
        "tags": ["低脂", "清淡"],
        "ingredients": [
            ("小白菜", 1, "把", "蔬菜"),
            ("蒜", 3, "瓣", "调味"),
            ("盐", None, "适量", "调味"),
            ("食用油", None, "适量", "调味"),
        ],
        "steps": [
            "小白菜洗净切段，蒜切片。",
            "热锅倒油，下蒜片爆香。",
            "放入小白菜大火快炒 1 分钟。",
            "加盐调味，断生立刻出锅。",
        ],
    },
    {
        "name": "香菇炖鸡",
        "image_url": "assets/images/mushroom-chicken.jpg",
        "description": "滋补养生，香气浓郁",
        "duration_minutes": 40,
        "servings": 3,
        "difficulty": "中等",
        "category": "炖菜",
        "season_recommendation": "秋季",
        "tips": "泡香菇的水别倒，加进去一起炖更香。",
        "tags": ["秋季推荐", "家常"],
        "ingredients": [
            ("鸡腿肉", 500, "克", "肉蛋"),
            ("干香菇", 8, "朵", "蔬菜"),
            ("姜", 3, "片", "调味"),
            ("生抽", 2, "勺", "调味"),
            ("料酒", 1, "勺", "调味"),
        ],
        "steps": [
            "干香菇提前用温水泡发，泡香菇的水留着别倒。",
            "鸡腿肉切块，冷水下锅焯去血水。",
            "锅中放油，下姜片和鸡块翻炒，加生抽、料酒上色。",
            "加入香菇和泡香菇的水，小火炖 30 分钟收汁。",
        ],
    },
]


# =====================================================================
# 灌数据
# =====================================================================


def _seed_user(
    session: Session,
    *,
    username: str,
    password: str,
    nickname: str,
    family_size: int,
    is_admin: bool = False,
) -> User:
    user = session.exec(select(User).where(User.username == username)).first()
    if user is not None:
        return user

    user = User(
        username=username,
        email=f"{username}@shishi.local",
        # 同样只存哈希 —— 种子数据也不破例
        password_hash=hash_password(password),
        nickname=nickname,
        family_size=family_size,
        is_admin=is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    session.add(
        UserPreference(
            user_id=user.id,
            taste="清淡",
            diet_style="家常",
            avoid_foods=["辛辣"],
            favorite_categories=["家常", "清淡"],
        )
    )
    session.commit()
    return user


def _seed_users(session: Session) -> None:
    """两个开箱可用的账号：演示用户 + 管理员。"""
    _seed_user(
        session,
        username=DEMO_USERNAME,
        password=DEMO_PASSWORD,
        nickname=DEMO_NICKNAME,
        family_size=DEMO_FAMILY_SIZE,
    )
    _seed_user(
        session,
        username=ADMIN_USERNAME,
        password=ADMIN_PASSWORD,
        nickname="管理员",
        family_size=3,
        is_admin=True,
    )


def _seed_foods(session: Session) -> None:
    if session.exec(select(Food)).first() is not None:
        return

    for item in _FOODS:
        season_name, start_month, end_month, score = item["season"]
        food = Food(
            name=item["name"],
            category=item["category"],
            image_url=item["image_url"],
            description=item["description"],
            nutrition_summary=item["nutrition_summary"],
            texture=item["texture"],
            common_methods=item["common_methods"],
            tags=item["tags"],
        )
        session.add(food)
        session.commit()
        session.refresh(food)

        session.add(
            FoodSeason(
                food_id=food.id,
                region="national",
                start_month=start_month,
                end_month=end_month,
                season_name=season_name,
                season_score=score,
                description=f"{item['name']}的{season_name}时令",
            )
        )
    session.commit()


def _seed_recipes(session: Session) -> None:
    if session.exec(select(Recipe)).first() is not None:
        return

    # 名称 → 食材 id，用于把配料关联到食材库
    food_ids = {f.name: f.id for f in session.exec(select(Food)).all()}

    for item in _RECIPES:
        recipe = Recipe(
            name=item["name"],
            image_url=item["image_url"],
            description=item["description"],
            duration_minutes=item["duration_minutes"],
            servings=item["servings"],
            difficulty=item["difficulty"],
            category=item["category"],
            season_recommendation=item["season_recommendation"],
            tips=item["tips"],
            tags=item["tags"],
        )
        session.add(recipe)
        session.commit()
        session.refresh(recipe)

        for name, amount, unit, category in item["ingredients"]:
            session.add(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    food_id=food_ids.get(name),
                    ingredient_name=name,
                    amount=amount,
                    unit=unit,
                    category=category,
                )
            )

        for index, text in enumerate(item["steps"], start=1):
            session.add(
                RecipeStep(
                    recipe_id=recipe.id,
                    step_no=index,
                    title=f"第 {index} 步",
                    description=text,
                )
            )
    session.commit()


def seed_all(session: Session) -> None:
    """灌全部种子数据。幂等 —— 重复调用不会重复插入。"""
    _seed_users(session)
    _seed_foods(session)
    _seed_recipes(session)


if __name__ == "__main__":
    with Session(engine) as session:
        seed_all(session)
    print("种子数据已灌入")
