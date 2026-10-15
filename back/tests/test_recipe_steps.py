import pytest
from app.utils.recipe_steps import clean_step_description, parse_recipe_steps


def test_two_digit_numbering_is_not_split():
    source = "\n".join(f"{i}. 做法{i}" for i in range(1, 22))
    assert parse_recipe_steps(source) == [f"做法{i}" for i in range(1, 22)]


@pytest.mark.parametrize(("source", "expected"), [
    ("1. 加1.5克盐，泡2小时\n2. 压20-30分钟", ["加1.5克盐，泡2小时", "压20-30分钟"]),
    ("1、洗净2、切块3、煮熟", ["洗净", "切块", "煮熟"]),
    ("第一步：洗净\n第二步：切块\n第三步：煮熟", ["洗净", "切块", "煮熟"]),
    ("一、洗净\n二、切块", ["洗净", "切块"]),
    ("1. 煮熟\n保持小火\n2. 盛出", ["煮熟\n保持小火", "盛出"]),
    ("洗净\n切块\n煮熟", ["洗净", "切块", "煮熟"]),
    ("加1.5克盐，按1:2兑水，煮20分钟", ["加1.5克盐，按1:2兑水，煮20分钟"]),
    ("1.\n洗净\n2.\n切块", ["洗净", "切块"]),
    ("１．洗净\n２．切块", ["洗净", "切块"]),
    ("", []),
])
def test_parse_steps_preserves_content(source, expected):
    assert parse_recipe_steps(source) == expected


@pytest.mark.parametrize("source", ["10. 炒香", "10、炒香", "第十步：炒香", "１０．炒香"])
def test_strip_existing_number_once(source):
    assert clean_step_description(source) == "炒香"


def test_decimal_at_start_is_not_a_step_number():
    assert clean_step_description("1.5克盐") == "1.5克盐"
