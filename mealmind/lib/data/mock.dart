import '../models/content.dart';

/// =====================================================================
/// 假数据 —— 内容与队友的网页原型 `team/dist/app.js` 完全一致
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
  ),
  Recipe(
    id: 'egg',
    name: '番茄炒蛋',
    image: 'assets/images/tomato-egg.jpg',
    desc: '酸甜开胃，经典家常',
    time: '15分钟',
    people: '2-3人',
    tags: ['快手菜', '下饭'],
  ),
  Recipe(
    id: 'cabbage',
    name: '清炒白菜',
    image: 'assets/images/cabbage.jpg',
    desc: '清爽脆嫩，简单快手',
    time: '10分钟',
    people: '2-3人',
    tags: ['低脂', '清淡'],
  ),
  Recipe(
    id: 'chicken',
    name: '香菇炖鸡',
    image: 'assets/images/mushroom-chicken.jpg',
    desc: '滋补养生，香气浓郁',
    time: '40分钟',
    people: '3人',
    tags: ['秋季推荐', '家常'],
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
