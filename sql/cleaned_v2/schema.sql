-- 菜谱数据库 V2：基础原生食材版（utf8mb4）
SET NAMES utf8mb4;

CREATE TABLE ingredient_categories (
  id INT PRIMARY KEY, name VARCHAR(50) NOT NULL UNIQUE, sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_subcategories (
  id INT PRIMARY KEY, category_id INT NOT NULL, name VARCHAR(50) NOT NULL, sort_order INT NOT NULL DEFAULT 0,
  UNIQUE KEY uk_sub(category_id,name), FOREIGN KEY(category_id) REFERENCES ingredient_categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredients (
  id INT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, category_id INT NOT NULL, subcategory_id INT NOT NULL,
  usage_count INT NOT NULL DEFAULT 0, is_core_raw TINYINT(1) NOT NULL DEFAULT 1,
  edible DECIMAL(8,2), water DECIMAL(10,3), energy_kcal DECIMAL(10,3), energy_kj DECIMAL(10,3),
  protein DECIMAL(10,3), fat DECIMAL(10,3), cho DECIMAL(10,3), dietary_fiber DECIMAL(10,3), cholesterol DECIMAL(10,3), ash DECIMAL(10,3),
  vitamin_a DECIMAL(12,3), carotene DECIMAL(12,3), retinol DECIMAL(12,3), thiamin DECIMAL(10,4), riboflavin DECIMAL(10,4), niacin DECIMAL(10,4),
  vitamin_c DECIMAL(10,3), vitamin_e DECIMAL(10,3), ca DECIMAL(12,3), p DECIMAL(12,3), k DECIMAL(12,3), na DECIMAL(12,3), mg DECIMAL(12,3),
  fe DECIMAL(10,3), zn DECIMAL(10,3), se DECIMAL(10,3), cu DECIMAL(10,3), mn DECIMAL(10,3),
  nutrition_source VARCHAR(200), nutrition_match VARCHAR(20), quality VARCHAR(20), category_source VARCHAR(30),
  tcm_user TEXT, tcm_not_user TEXT,
  FOREIGN KEY(category_id) REFERENCES ingredient_categories(id), FOREIGN KEY(subcategory_id) REFERENCES ingredient_subcategories(id),
  KEY idx_ingredients_name(name), KEY idx_ingredients_usage(usage_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE tcm_effects (id INT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE target_groups (id INT PRIMARY KEY, name VARCHAR(200) NOT NULL UNIQUE, is_suitable TINYINT(1) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_effects (
  ingredient_id INT NOT NULL, effect_id INT NOT NULL, PRIMARY KEY(ingredient_id,effect_id),
  FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE, FOREIGN KEY(effect_id) REFERENCES tcm_effects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_groups (
  ingredient_id INT NOT NULL, group_id INT NOT NULL, PRIMARY KEY(ingredient_id,group_id),
  FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE, FOREIGN KEY(group_id) REFERENCES target_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dishes (
  id INT PRIMARY KEY, dish_name VARCHAR(255) NOT NULL, description TEXT, cuisine VARCHAR(50), ingredient_text MEDIUMTEXT, instruction_text MEDIUMTEXT,
  ingredient_count INT NOT NULL DEFAULT 0, main_ingredient_count INT NOT NULL DEFAULT 0, total_weight_g DECIMAL(12,2), KEY idx_dish_name(dish_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_ingredients (
  id BIGINT PRIMARY KEY, dish_id INT NOT NULL, ingredient_id INT NULL, raw_name VARCHAR(255) NOT NULL, raw_text VARCHAR(500) NOT NULL,
  quantity VARCHAR(100), role VARCHAR(20) NOT NULL, grams DECIMAL(12,3), grams_source VARCHAR(30),
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE, FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  KEY idx_di_dish(dish_id), KEY idx_di_ing(ingredient_id), KEY idx_di_role(role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE tags (id INT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, kind VARCHAR(20)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_tags (
  dish_id INT NOT NULL, tag_id INT NOT NULL, PRIMARY KEY(dish_id,tag_id),
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE, FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_nutrition (
  dish_id INT PRIMARY KEY, total_weight_g DECIMAL(12,2), energy_kcal DECIMAL(12,3), protein_g DECIMAL(12,3), fat_g DECIMAL(12,3), cho_g DECIMAL(12,3),
  dietary_fiber_g DECIMAL(12,3), ca_mg DECIMAL(12,3), fe_mg DECIMAL(12,3), na_mg DECIMAL(12,3), matched_ratio DECIMAL(8,3), weight_confidence DECIMAL(8,3),
  explicit_count INT, estimated_count INT, vague_count INT, suspect TINYINT(1) NOT NULL DEFAULT 0, nutrition_version VARCHAR(20) NOT NULL DEFAULT 'legacy',
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonings (id INT PRIMARY KEY, name VARCHAR(200) NOT NULL UNIQUE, usage_count INT NOT NULL DEFAULT 0, reason VARCHAR(255)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE excluded_names (id INT PRIMARY KEY, name VARCHAR(255) NOT NULL, usage_count INT NOT NULL DEFAULT 0, reason VARCHAR(255), KEY idx_excluded_name(name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
