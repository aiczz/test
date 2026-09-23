-- 菜谱数据库 V2 精简运行结构：6 张业务表（utf8mb4）
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS seasonal_dish_links, seasonal_knowledge, seasonal_food, seasonal_calendar,
  dish_nutrition, dish_tags, tags, dish_ingredient_search, dish_ingredient_components,
  dish_ingredients, dishes, ingredient_catalog_aliases, ingredient_catalog,
  ingredient_hierarchy, ingredient_groups, ingredient_effects, target_groups, tcm_effects,
  excluded_names, seasonings, ingredients, ingredient_subcategories, ingredient_categories;
SET FOREIGN_KEY_CHECKS=1;

CREATE TABLE ingredients (
  id INT PRIMARY KEY,
name VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_bin
    NOT NULL UNIQUE,
ingredient_type VARCHAR(30) NOT NULL,
  core_ingredient_id INT NULL, category VARCHAR(50) NOT NULL, subcategory VARCHAR(50) NOT NULL,
  is_core_raw TINYINT(1) NOT NULL DEFAULT 0, is_edible TINYINT(1) NOT NULL DEFAULT 1,
  review_status VARCHAR(20) NOT NULL, usage_count INT NOT NULL DEFAULT 0, reason VARCHAR(255),
  edible DECIMAL(8,2), water DECIMAL(10,3), energy_kcal DECIMAL(10,3), energy_kj DECIMAL(10,3),
  protein DECIMAL(10,3), fat DECIMAL(10,3), cho DECIMAL(10,3), dietary_fiber DECIMAL(10,3), cholesterol DECIMAL(10,3), ash DECIMAL(10,3),
  vitamin_a DECIMAL(12,3), carotene DECIMAL(12,3), retinol DECIMAL(12,3), thiamin DECIMAL(10,4), riboflavin DECIMAL(10,4), niacin DECIMAL(10,4),
  vitamin_c DECIMAL(10,3), vitamin_e DECIMAL(10,3), ca DECIMAL(12,3), p DECIMAL(12,3), k DECIMAL(12,3), na DECIMAL(12,3), mg DECIMAL(12,3),
  fe DECIMAL(10,3), zn DECIMAL(10,3), se DECIMAL(10,3), cu DECIMAL(10,3), mn DECIMAL(10,3),
  nutrition_source VARCHAR(200), nutrition_match VARCHAR(50), quality VARCHAR(20), category_source VARCHAR(30),
  tcm_user TEXT, tcm_not_user TEXT,
  effects_json JSON NOT NULL, suitable_groups_json JSON NOT NULL, unsuitable_groups_json JSON NOT NULL,
  aliases_json JSON NOT NULL, parent_core_ids_json JSON NOT NULL, child_core_ids_json JSON NOT NULL,
  FOREIGN KEY(core_ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  KEY idx_ingredients_type(ingredient_type), KEY idx_ingredients_core(core_ingredient_id),
  KEY idx_ingredients_category(category), KEY idx_ingredients_usage(usage_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dishes (
  id INT PRIMARY KEY, dish_name VARCHAR(255) NOT NULL, dish_name_original VARCHAR(255) NOT NULL,
  description TEXT, cuisine VARCHAR(50), ingredient_text MEDIUMTEXT, instruction_text MEDIUMTEXT,
  ingredient_count INT NOT NULL DEFAULT 0, main_ingredient_count INT NOT NULL DEFAULT 0,
  search_ingredient_count INT NOT NULL DEFAULT 0, total_weight_g DECIMAL(12,2),
  energy_kcal DECIMAL(12,3), protein_g DECIMAL(12,3), fat_g DECIMAL(12,3), cho_g DECIMAL(12,3),
  dietary_fiber_g DECIMAL(12,3), ca_mg DECIMAL(12,3), fe_mg DECIMAL(12,3), na_mg DECIMAL(12,3),
  matched_ratio DECIMAL(8,3), weight_confidence DECIMAL(8,3), explicit_count INT, estimated_count INT,
  vague_count INT, suspect TINYINT(1) NOT NULL DEFAULT 0, nutrition_version VARCHAR(20) NOT NULL,
  tags_json JSON NOT NULL, search_ingredient_ids_json JSON NOT NULL,
  KEY idx_dish_name(dish_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_ingredients (
  id BIGINT PRIMARY KEY, dish_id INT NOT NULL, ingredient_id INT NOT NULL, core_ingredient_id INT NULL,
  raw_name VARCHAR(255) NOT NULL, raw_text VARCHAR(500) NOT NULL,
  quantity VARCHAR(100), role VARCHAR(20) NOT NULL, grams DECIMAL(12,3), grams_source VARCHAR(30),
  component_core_ids_json JSON NOT NULL,
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE,
  FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE RESTRICT,
  FOREIGN KEY(core_ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  KEY idx_di_dish(dish_id), KEY idx_di_ing(ingredient_id), KEY idx_di_core(core_ingredient_id), KEY idx_di_role(role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonal_calendar (
  id VARCHAR(50) PRIMARY KEY, level VARCHAR(20) NOT NULL, name VARCHAR(50) NOT NULL,
  gregorian_time VARCHAR(100), lunar_time VARCHAR(100), season VARCHAR(10) NOT NULL,
  sort_order INT NOT NULL, description VARCHAR(500), knowledge_json JSON NOT NULL,
  UNIQUE KEY uk_seasonal_calendar_level_name(level,name), KEY idx_seasonal_calendar_sort(sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonal_food (
  id VARCHAR(20) PRIMARY KEY, calendar_id VARCHAR(50) NOT NULL, level VARCHAR(20) NOT NULL,
  time_name VARCHAR(50) NOT NULL, season VARCHAR(10) NOT NULL, category VARCHAR(20) NOT NULL,
  name VARCHAR(100) NOT NULL, note VARCHAR(500), recommendation_reason VARCHAR(500), source VARCHAR(100) NOT NULL,
  entity_type VARCHAR(30) NOT NULL, ingredient_id INT NULL, core_ingredient_id INT NULL,
  match_status VARCHAR(40) NOT NULL, knowledge_json JSON NOT NULL,
  UNIQUE KEY uk_seasonal_food(calendar_id,category,name),
  FOREIGN KEY(calendar_id) REFERENCES seasonal_calendar(id) ON DELETE CASCADE,
  FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  FOREIGN KEY(core_ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  KEY idx_seasonal_food_name(name), KEY idx_seasonal_food_ingredient(ingredient_id), KEY idx_seasonal_food_season(season)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonal_dish_links (
  seasonal_food_id VARCHAR(20) NOT NULL, dish_id INT NOT NULL, match_type VARCHAR(30) NOT NULL,
  PRIMARY KEY(seasonal_food_id,dish_id),
  FOREIGN KEY(seasonal_food_id) REFERENCES seasonal_food(id) ON DELETE CASCADE,
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE,
  KEY idx_seasonal_dish_links_dish(dish_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
