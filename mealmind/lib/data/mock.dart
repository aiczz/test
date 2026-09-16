import '../models/content.dart';

/// =====================================================================
/// 假数据 —— 内容与队友的网页原型 `dist/app.js` 一致
///
/// 后端接口好了之后，这个文件会被 lib/services/api.dart 的真实请求替代。
/// 现在前端不等待后端，先按这份数据把界面做完。
/// =====================================================================

const mockFoods = <Food>[
  Food(
    id: 'lotus',
    name: '莲藕',
    image: 'assets/images/lotus.jpg',
    category: '蔬菜',
    qty: '1节',
    tags: ['润燥养胃', '秋季适宜'],
  ),
  Food(
    id: 'pumpkin',
    name: '南瓜',
    image: 'assets/images/pumpkin.jpg',
    category: '蔬菜',
    qty: '半个',
    tags: ['富含膳食纤维', '软糯香甜'],
  ),
  Food(
    id: 'tomato',
    name: '西红柿',
    image: 'assets/images/tomato.jpg',
    category: '蔬菜',
    qty: '5个',
    tags: ['富含维生素C', '酸甜开胃'],
  ),
  Food(
    id: 'bokchoy',
    name: '小白菜',
    image: 'assets/images/bokchoy.jpg',
    category: '蔬菜',
    qty: '1把',
    tags: ['清爽鲜嫩', '家常常备'],
  ),
  Food(
    id: 'carrot',
    name: '胡萝卜',
    image: 'assets/images/carrot.jpg',
    category: '蔬菜',
    qty: '2根',
    tags: ['富含胡萝卜素', '增强免疫'],
  ),
  Food(
    id: 'egg',
    name: '鸡蛋',
    image: 'assets/images/egg.jpg',
    category: '肉蛋',
    qty: '3个',
    tags: ['优质蛋白', '营养全面'],
  ),
];

const mockRecipes = <Recipe>[
  Recipe(
    id: 'soup',
    name: '莲藕排骨汤',
    image: 'assets/images/hero-soup.jpg',
    desc: '清甜滋补，秋日暖汤',
    time: '60分钟',
    people: '2-3人',
    tags: ['秋日暖汤', '家常', '营养'],
    difficulty: '简单',
    ingredients: ['莲藕 1节', '排骨 500克', '胡萝卜 1根', '姜 3片', '葱 2根', '盐 适量'],
    steps: [
      '排骨冷水下锅焯水，煮开后捞出冲洗干净。',
      '莲藕和胡萝卜去皮切块，姜切片，葱切段备用。',
      '所有食材放入锅中，加足量清水，大火煮开后转小火慢炖 40 分钟。',
      '出锅前加盐调味，撒上葱花即可。',
    ],
  ),
  Recipe(
    id: 'egg',
    name: '番茄炒蛋',
    image: 'assets/images/tomato-egg.jpg',
    desc: '酸甜开胃，经典家常',
    time: '15分钟',
    people: '2-3人',
    tags: ['快手菜', '下饭'],
    difficulty: '简单',
    ingredients: ['西红柿 3个', '鸡蛋 4个', '葱 1根', '糖 1小勺', '盐 适量'],
    steps: [
      '鸡蛋打散加少许盐搅匀，西红柿切块，葱切末。',
      '热锅倒油，倒入蛋液炒至刚凝固就盛出（别炒老）。',
      '锅中留底油，下西红柿炒出汁，加糖和盐调味。',
      '倒回炒好的鸡蛋翻炒均匀，撒葱花出锅。',
    ],
  ),
  Recipe(
    id: 'cabbage',
    name: '清炒白菜',
    image: 'assets/images/cabbage.jpg',
    desc: '清爽脆嫩，简单快手',
    time: '10分钟',
    people: '2-3人',
    tags: ['低脂', '清淡'],
    difficulty: '简单',
    ingredients: ['小白菜 1把', '蒜 3瓣', '盐 适量', '食用油 适量'],
    steps: [
      '小白菜洗净切段，蒜切片。',
      '热锅倒油，下蒜片爆香。',
      '放入小白菜大火快炒 1 分钟。',
      '加盐调味，断生立刻出锅 —— 久炒会出水变软。',
    ],
  ),
  Recipe(
    id: 'chicken',
    name: '香菇炖鸡',
    image: 'assets/images/mushroom-chicken.jpg',
    desc: '滋补养生，香气浓郁',
    time: '40分钟',
    people: '3人',
    tags: ['秋季推荐', '家常'],
    difficulty: '中等',
    ingredients: ['鸡腿肉 500克', '干香菇 8朵', '姜 3片', '生抽 2勺', '料酒 1勺'],
    steps: [
      '干香菇提前用温水泡发，泡香菇的水留着别倒。',
      '鸡腿肉切块，冷水下锅焯去血水。',
      '锅中放油，下姜片和鸡块翻炒，加生抽、料酒上色。',
      '加入香菇和泡香菇的水，小火炖 30 分钟收汁。',
    ],
  ),
];

const mockAiTip = AiTip(
  title: '小食同学的今日建议',
  body: '今天昼夜温差较大，晚餐适合搭配一道暖汤和一份清爽时蔬。',
);

/// 首页 hero 文案
const heroEyebrow = '今日推荐 · 杭州';
const heroTitle = '今天吃什么';
const heroBody = '秋天正是莲藕上市的好时节。来一碗莲藕排骨汤，润燥又养胃。';

/// 顶部两个 pill 的文案
const currentCity = '杭州';
const currentSeason = '秋季 · 9月';

// =====================================================================
// AI 助手 —— 多智能体协作轨迹（假数据）
//
// 真实的轨迹由后端返回（每个 Agent 一步）。
// 这里先按设计好的流程写死，让"多智能体"在演示时看得见。
// =====================================================================

const mockAgentTrace = <AgentStep>[
  AgentStep(
    agent: 'Profile Agent',
    summary: '读取家庭档案：3 人 · 周预算 300 元 · 妈妈限钠 · 孩子不吃辣',
    ms: 12,
  ),
  AgentStep(
    agent: 'Retrieval Agent',
    summary: '候选召回 42 道 → 过滤过敏原与辣味后剩 31 道',
    ms: 86,
  ),
  AgentStep(
    agent: 'Inventory Agent',
    summary: '库存与保质期检查：菠菜周四到期，需优先消耗',
    status: 'info',
    ms: 9,
  ),
  AgentStep(
    agent: 'Nutrition Agent',
    summary: '营养校验：钠 1720 / 2000 mg ✓ 蔬菜量达标 ✓',
    ms: 24,
  ),
  AgentStep(
    agent: 'Planner Agent',
    summary: 'CP-SAT 求解完成，生成 3 个 Pareto 方案',
    ms: 1840,
  ),
  AgentStep(
    agent: 'Critic Agent',
    summary: '否决方案 B（钠 2180 mg 超标），回灌 Planner 重解',
    status: 'veto',
    ms: 31,
  ),
  AgentStep(
    agent: 'Explainer Agent',
    summary: '生成推荐理由与约束松紧说明',
    ms: 402,
  ),
];

const mockAiGreeting = '你好，我是小食。现在是秋季，需要我帮你安排一顿简单又营养的晚餐吗？';

const mockAiQuickPrompts = <String>[
  '今天吃什么？',
  '三人晚餐推荐',
  '用家里的食材做菜',
];

/// 两种回复：问到「食材」走第一种，否则走第二种（与原型逻辑一致）
const mockAiReplyByFood = '你家现有的番茄、鸡蛋和小白菜很适合做番茄炒蛋与清炒白菜，'
    '再搭配莲藕排骨汤，就是一顿营养均衡的三人晚餐。';

const mockAiReplyDefault = '结合杭州秋季时令，我推荐莲藕排骨汤、番茄炒蛋和清炒白菜。'
    '荤素搭配，味道温和，适合 2–3 人。';

