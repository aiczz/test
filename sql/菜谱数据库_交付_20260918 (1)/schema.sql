-- ============================================================================
-- 菜谱库 · 精简版表结构（11 张表）
-- ============================================================================
-- 设计原则：只保留 App 真正要用的。
-- 已删掉的冗余：见文件末尾「不做的事」。
--
-- 字符集一律 utf8mb4
-- ============================================================================

SET NAMES utf8mb4;

-- ============================================================================
-- 一、食材维度（6 张表）
-- ============================================================================

-- 1. 食材大类（15 个，来自《中国食物成分表》）
CREATE TABLE ingredient_categories (
    id         INT PRIMARY KEY AUTO_INCREMENT,
    name       VARCHAR(50) NOT NULL UNIQUE,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='食材大类';

-- 2. 食材子类（61 个）
CREATE TABLE ingredient_subcategories (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    category_id INT NOT NULL,
    name        VARCHAR(50) NOT NULL,
    sort_order  INT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_cat_name (category_id, name),
    CONSTRAINT fk_sub_cat FOREIGN KEY (category_id)
        REFERENCES ingredient_categories(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='食材子类';

-- 3. 食材主表 ★核心
--    营养素单位一律为「每 100g 可食部」
--    【不含调味料】
CREATE TABLE ingredients (
    id             INT PRIMARY KEY AUTO_INCREMENT,
    name           VARCHAR(100) NOT NULL UNIQUE COMMENT '规范食材名',
    category_id    INT DEFAULT NULL,
    subcategory_id INT DEFAULT NULL,
    usage_count    INT NOT NULL DEFAULT 0 COMMENT '在下厨房语料里被引用次数',

    -- 营养素（可为空，表示该食材没匹配到成分表）
    edible         DECIMAL(6,1)  COMMENT '可食部 %',
    water          DECIMAL(8,2)  COMMENT '水分 g',
    energy_kcal    DECIMAL(8,1)  COMMENT '能量 kcal',
    protein        DECIMAL(8,2)  COMMENT '蛋白质 g',
    fat            DECIMAL(8,2)  COMMENT '脂肪 g',
    cho            DECIMAL(8,2)  COMMENT '碳水化合物 g',
    dietary_fiber  DECIMAL(8,2)  COMMENT '膳食纤维 g',
    cholesterol    DECIMAL(8,1)  COMMENT '胆固醇 mg',
    vitamin_a      DECIMAL(10,1) COMMENT '维生素A ugRE',
    carotene       DECIMAL(10,1) COMMENT '胡萝卜素 ug',
    thiamin        DECIMAL(8,3)  COMMENT '硫胺素 mg',
    riboflavin     DECIMAL(8,3)  COMMENT '核黄素 mg',
    niacin         DECIMAL(8,3)  COMMENT '烟酸 mg',
    vitamin_c      DECIMAL(8,1)  COMMENT '维生素C mg',
    vitamin_e      DECIMAL(8,2)  COMMENT '维生素E mg',
    ca             DECIMAL(10,1) COMMENT '钙 mg',
    p              DECIMAL(10,1) COMMENT '磷 mg',
    k              DECIMAL(10,1) COMMENT '钾 mg',
    na             DECIMAL(10,1) COMMENT '钠 mg',
    mg             DECIMAL(10,1) COMMENT '镁 mg',
    fe             DECIMAL(10,2) COMMENT '铁 mg',
    zn             DECIMAL(10,2) COMMENT '锌 mg',
    se             DECIMAL(10,2) COMMENT '硒 ug',
    cu             DECIMAL(10,2) COMMENT '铜 mg',
    mn             DECIMAL(10,2) COMMENT '锰 mg',
    nutrition_source VARCHAR(100) DEFAULT '' COMMENT '营养素来源条目名（可溯源）',

    -- 数据质量分级（App 展示与推荐计算只用 core + common）
    quality        VARCHAR(10) NOT NULL DEFAULT 'tail'
                   COMMENT 'core=成分表有权威数据 / common=语料引用>=20 / tail=长尾',
    category_source VARCHAR(20) DEFAULT ''
                   COMMENT 'nutrition_table=成分表原分类 / keyword=关键词兜底 / fallback=其他类-其他',

    -- 额外营养/热量字段（CSV 有，App 可选用）
    energy_kj      DECIMAL(8,1)  COMMENT '能量 kJ',
    ash            DECIMAL(8,2)  COMMENT '灰分 g',
    retinol        DECIMAL(10,1) COMMENT '视黄醇 ug',

    -- 中医适宜人群（原文文本，来自中医表 user 字段）
    tcm_user       TEXT COMMENT '适宜人群',
    tcm_not_user   TEXT COMMENT '不适宜人群',

    KEY idx_name (name),
    KEY idx_cat (category_id),
    KEY idx_usage (usage_count),
    CONSTRAINT fk_ing_cat FOREIGN KEY (category_id)
        REFERENCES ingredient_categories(id) ON DELETE SET NULL,
    CONSTRAINT fk_ing_sub FOREIGN KEY (subcategory_id)
        REFERENCES ingredient_subcategories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='食材主表';

-- 4. 中医功效字典
CREATE TABLE tcm_effects (
    id   INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中医功效字典';

-- 5. 食材-功效（食材的 tag）
CREATE TABLE ingredient_effects (
    ingredient_id INT NOT NULL,
    effect_id     INT NOT NULL,
    PRIMARY KEY (ingredient_id, effect_id),
    CONSTRAINT fk_ie_ing FOREIGN KEY (ingredient_id)
        REFERENCES ingredients(id) ON DELETE CASCADE,
    CONSTRAINT fk_ie_eff FOREIGN KEY (effect_id)
        REFERENCES tcm_effects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='食材-功效（tag）';

-- 6. 适宜人群字典 + 关联
CREATE TABLE target_groups (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(200) NOT NULL UNIQUE,
    is_suitable TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1=适宜 0=不适宜'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人群字典';

CREATE TABLE ingredient_groups (
    ingredient_id INT NOT NULL,
    group_id      INT NOT NULL,
    PRIMARY KEY (ingredient_id, group_id),
    CONSTRAINT fk_ig_ing FOREIGN KEY (ingredient_id)
        REFERENCES ingredients(id) ON DELETE CASCADE,
    CONSTRAINT fk_ig_grp FOREIGN KEY (group_id)
        REFERENCES target_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='食材-人群（tag）';

-- ============================================================================
-- 二、菜品维度（5 张表）
-- ============================================================================

-- 7. 菜品主表 ★核心
--    ingredient_text  = 完整原材料字符串
--    instruction_text = 完整做法字符串
CREATE TABLE dishes (
    id               INT PRIMARY KEY AUTO_INCREMENT,
    dish_name        VARCHAR(255) NOT NULL,
    description      TEXT,
    cuisine          VARCHAR(50) DEFAULT '' COMMENT '菜系（语料字段，可能为空）',
    ingredient_text  TEXT       COMMENT '完整原材料字符串',
    instruction_text MEDIUMTEXT COMMENT '完整做法字符串',
    ingredient_count INT DEFAULT 0 COMMENT '用料条数',
    total_weight_g   DECIMAL(10,1) DEFAULT NULL COMMENT '可换算出的总重量（估算）',
    KEY idx_dish_name (dish_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='菜品主表';

-- 8. 菜品-食材 ★核心
--    「每道菜由若干食材构成」靠这张表
--    查一个食材能推到哪些菜：SELECT dish_id FROM dish_ingredients WHERE ingredient_id=?
CREATE TABLE dish_ingredients (
    id            INT PRIMARY KEY AUTO_INCREMENT,
    dish_id       INT NOT NULL,
    ingredient_id INT DEFAULT NULL COMMENT 'NULL=调味料或未匹配',
    raw_name      VARCHAR(255) NOT NULL COMMENT '归一后的用料名',
    raw_text      VARCHAR(255) NOT NULL COMMENT '原始完整字符串，如「2大片生菜」',
    quantity      VARCHAR(100) DEFAULT '' COMMENT '用量',
    role          VARCHAR(20)  DEFAULT '' COMMENT 'main=主料 seasoning=调味料 other=其他',
    grams         DECIMAL(10,1) DEFAULT NULL COMMENT '换算克数（估算）',
    grams_source  VARCHAR(20) DEFAULT '' COMMENT 'explicit/per_unit/category/vague',
    KEY idx_di_dish (dish_id),
    KEY idx_di_ing (ingredient_id),
    CONSTRAINT fk_di_dish FOREIGN KEY (dish_id)
        REFERENCES dishes(id) ON DELETE CASCADE,
    CONSTRAINT fk_di_ing FOREIGN KEY (ingredient_id)
        REFERENCES ingredients(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='菜品-食材（含用量）';

-- 9. 标签字典
CREATE TABLE tags (
    id   INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    kind VARCHAR(20) DEFAULT 'general'
         COMMENT 'general/cuisine/season/method/audience'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标签字典';

-- 10. 菜品-标签（菜品的 tag）
CREATE TABLE dish_tags (
    dish_id INT NOT NULL,
    tag_id  INT NOT NULL,
    PRIMARY KEY (dish_id, tag_id),
    CONSTRAINT fk_dt_dish FOREIGN KEY (dish_id)
        REFERENCES dishes(id) ON DELETE CASCADE,
    CONSTRAINT fk_dt_tag FOREIGN KEY (tag_id)
        REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='菜品-标签（tag）';

-- 11. 菜品营养（按用料克数加权算出，估算值）
CREATE TABLE dish_nutrition (
    dish_id         INT PRIMARY KEY,
    total_weight_g  DECIMAL(10,1),
    energy_kcal     DECIMAL(10,1),
    protein_g       DECIMAL(10,2),
    fat_g           DECIMAL(10,2),
    cho_g           DECIMAL(10,2),
    dietary_fiber_g DECIMAL(10,2),
    ca_mg           DECIMAL(10,1),
    fe_mg           DECIMAL(10,2),
    na_mg           DECIMAL(10,1),
    matched_ratio   DECIMAL(5,2) COMMENT '能匹配到营养数据的用料占比 %',
    weight_confidence DECIMAL(5,2) COMMENT '称重可信度 %',
    explicit_count  INT DEFAULT 0 COMMENT '用料里明确写了克数的条数',
    estimated_count INT DEFAULT 0 COMMENT '靠单重/类别均重估出来的条数',
    vague_count     INT DEFAULT 0 COMMENT '适量/少许（记为0g）的条数',
    suspect         TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1=数据不可用（超限），前端必须隐藏',
    CONSTRAINT fk_dn_dish FOREIGN KEY (dish_id)
        REFERENCES dishes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='菜品营养（估算）';

-- ============================================================================
-- 三、排除清单（不是数据表，是"我们主动去掉什么"的凭据）
-- ============================================================================

-- 12. 调味料（不进食材表，但菜谱用料里保留）
CREATE TABLE seasonings (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(100) NOT NULL UNIQUE,
    usage_count INT NOT NULL DEFAULT 0,
    reason      VARCHAR(50) DEFAULT '' COMMENT '剔除原因'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='调味料字典（不属于食材）';

-- 13. 剔除的非食材名（说明文字、份量词等）
CREATE TABLE excluded_names (
    id     INT PRIMARY KEY AUTO_INCREMENT,
    name   VARCHAR(200) NOT NULL,
    reason VARCHAR(50)  DEFAULT '',
    KEY idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='剔除的非食材名（审计凭据）';

-- ============================================================================
-- 不做的事（避免表膨胀）
-- ============================================================================
-- 1. 不做菜品-食材的「用量表」单独拆表 -- 用量就在 dish_ingredients.quantity 里
-- 2. 不做「做法分步骤表」        -- instruction_text 是完整字符串，不拆
-- 3. 不做食材别名表              -- 别名映射在清洗脚本里，用完即弃
-- 4. 不做中医性味字段            -- 源数据里没有，留空字段会误导
-- 5. 不做菜品营养的历史版本      -- 只需当前值
