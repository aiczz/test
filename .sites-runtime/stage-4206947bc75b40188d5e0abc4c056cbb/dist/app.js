const foods = [
  { id: 'lotus', name: '莲藕', image: 'assets/lotus.jpg', category: '蔬菜', qty: '1节', tags: ['润燥养胃', '秋季适宜'] },
  { id: 'pumpkin', name: '南瓜', image: 'assets/pumpkin.jpg', category: '蔬菜', qty: '半个', tags: ['富含膳食纤维', '软糯香甜'] },
  { id: 'tomato', name: '西红柿', image: 'assets/tomato.jpg', category: '蔬菜', qty: '5个', tags: ['富含维生素C', '酸甜开胃'] },
  { id: 'bokchoy', name: '小白菜', image: 'assets/bokchoy.jpg', category: '蔬菜', qty: '1把', tags: ['清爽鲜嫩', '家常常备'] },
  { id: 'carrot', name: '胡萝卜', image: 'assets/carrot.jpg', category: '蔬菜', qty: '2根', tags: ['富含胡萝卜素', '增强免疫'] },
  { id: 'egg', name: '鸡蛋', image: 'assets/egg.jpg', category: '肉蛋', qty: '3个', tags: ['优质蛋白', '营养全面'] },
];

const recipes = [
  { id: 'soup', name: '莲藕排骨汤', image: 'assets/hero-soup.jpg', desc: '清甜滋补，秋日暖汤', time: '60分钟', people: '2-3人', tags: ['秋日暖汤', '家常', '营养'] },
  { id: 'egg', name: '番茄炒蛋', image: 'assets/tomato-egg.jpg', desc: '酸甜开胃，经典家常', time: '15分钟', people: '2-3人', tags: ['快手菜', '下饭'] },
  { id: 'cabbage', name: '清炒白菜', image: 'assets/cabbage.jpg', desc: '清爽脆嫩，简单快手', time: '10分钟', people: '2-3人', tags: ['低脂', '清淡'] },
  { id: 'chicken', name: '香菇炖鸡', image: 'assets/mushroom-chicken.jpg', desc: '滋补养生，香气浓郁', time: '40分钟', people: '3人', tags: ['秋季推荐', '家常'] },
];

const navItems = [
  ['home', '⌂', '首页'],
  ['foods', '◒', '食材'],
  ['recipes', '▤', '菜谱'],
  ['ai', '◉', 'AI助手'],
  ['profile', '♙', '我的'],
];

const state = {
  route: location.hash.replace('#', '') || 'home',
  favorites: new Set(['soup']),
  foodFilter: '全部',
  recipeFilter: '全部',
  messages: [],
  shopping: [
    ['莲藕', '1节', true, '蔬菜'], ['番茄', '5个', false, '蔬菜'], ['胡萝卜', '2根', false, '蔬菜'],
    ['鸡蛋', '12个', true, '肉蛋'], ['排骨', '500g', false, '肉蛋'], ['姜', '1块', true, '调味'], ['葱', '2根', false, '调味'],
  ]
};

const view = document.querySelector('#view');
const detailDialog = document.querySelector('#detailDialog');
const shoppingDialog = document.querySelector('#shoppingDialog');

function navMarkup() {
  return navItems.map(([id, icon, label]) => `
    <button class="nav-button ${state.route === id ? 'active' : ''}" data-route="${id}" aria-current="${state.route === id ? 'page' : 'false'}">
      <span class="nav-icon">${icon}</span><span>${label}</span>
    </button>`).join('');
}

function updateNav() {
  document.querySelectorAll('.rail-nav, .bottom-nav').forEach(el => el.innerHTML = navMarkup());
}

function favoriteButton(id) {
  return `<button class="favorite ${state.favorites.has(id) ? 'on' : ''}" data-favorite="${id}" aria-label="${state.favorites.has(id) ? '取消收藏' : '收藏'}">${state.favorites.has(id) ? '♥' : '♡'}</button>`;
}

function recipeCard(recipe) {
  return `<article class="card recipe-card">
    ${favoriteButton(recipe.id)}
    <div class="card-image"><img src="${recipe.image}" alt="${recipe.name}" /></div>
    <div class="card-body">
      <h3>${recipe.name}</h3><p>${recipe.desc}</p>
      <div class="tags">${recipe.tags.slice(0,2).map((tag, i) => `<span class="tag ${i === 0 ? 'warm' : ''}">${tag}</span>`).join('')}</div>
      <div class="meta"><span>◷ ${recipe.time}</span><span>♙ ${recipe.people}</span></div>
    </div>
    <button class="card-hit" data-recipe="${recipe.id}" aria-label="查看${recipe.name}"></button>
  </article>`;
}

function foodCard(food, inventory = false) {
  return `<article class="card ${inventory ? 'inventory-card' : ''}" data-category="${food.category}">
    <div class="card-image"><img src="${food.image}" alt="${food.name}" /></div>
    <div class="card-body">
      <h3>${food.name}</h3>
      ${inventory ? `<p class="qty">${food.qty}</p>` : ''}
      <div class="tags">${food.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}</div>
    </div>
  </article>`;
}

function sectionHeader(icon, title, subtitle, action = '') {
  return `<div class="section-header"><div class="section-title"><span class="section-icon">${icon}</span><div><h2>${title}</h2><p>${subtitle}</p></div></div>${action ? `<button class="text-button" data-action="${action}">查看更多 ›</button>` : ''}</div>`;
}

function homePage() {
  return `
    <section class="hero">
      <div class="hero-copy">
        <span class="eyebrow">今日推荐 · 杭州</span>
        <h1>今天吃什么</h1>
        <p>秋天正是莲藕上市的好时节。来一碗莲藕排骨汤，润燥又养胃。</p>
        <button class="primary" data-recipe="soup">查看推荐菜谱 →</button>
      </div>
      <div class="hero-image"><img src="assets/hero-soup.jpg" alt="秋季莲藕排骨汤" /></div>
    </section>
    <section class="section">
      ${sectionHeader('◒', '今日推荐食材', '应季鲜美 · 营养加分', 'foods')}
      <div class="card-grid">${foods.slice(0,3).map(food => foodCard(food)).join('')}</div>
    </section>
    <section class="section">
      ${sectionHeader('♨', '家常易做推荐', '应季食材 · 简单好做', 'recipes')}
      <div class="card-grid">${recipes.slice(0,3).map(recipeCard).join('')}</div>
    </section>
    <section class="section ai-tip">
      <span class="tip-icon">✦</span>
      <div><strong>小食同学的今日建议</strong><p>今天昼夜温差较大，晚餐适合搭配一道暖汤和一份清爽时蔬。</p></div>
    </section>
    <div class="quick-actions"><button class="secondary" data-action="today-menu">查看今日菜单</button><button class="primary" data-route="foods">去选食材</button></div>`;
}

function foodsPage() {
  const categories = ['全部', '蔬菜', '肉蛋', '水产', '豆制品'];
  const list = state.foodFilter === '全部' ? foods : foods.filter(f => f.category === state.foodFilter);
  return `
    <section class="page-intro">
      <div><span class="eyebrow">我的厨房</span><h1>现有食材</h1><p>看看家里有什么，搭配更省心，也减少浪费。</p></div>
      <img src="assets/pantry.jpg" alt="一篮新鲜时令食材" />
    </section>
    <div class="segmented">${categories.map(c => `<button class="chip ${state.foodFilter === c ? 'active' : ''}" data-food-filter="${c}">${c}</button>`).join('')}</div>
    <section class="section">
      ${sectionHeader('◒', `我家的食材（${list.length}）`, '点击分类快速筛选')}
      <div class="inventory-grid">${list.length ? list.map(f => foodCard(f, true)).join('') : '<div class="empty">这个分类还没有食材</div>'}</div>
      <button class="primary wide-cta" data-action="cook-with-foods">♨ 用这些食材做菜 →</button>
    </section>`;
}

function recipesPage() {
  const categories = ['全部', '快手菜', '汤品', '低脂', '家常', '秋季推荐'];
  let list = recipes;
  if (state.recipeFilter !== '全部') list = recipes.filter(r => r.tags.includes(state.recipeFilter) || (state.recipeFilter === '汤品' && r.id === 'soup'));
  return `
    <section class="page-intro"><div><span class="eyebrow">时令菜谱</span><h1>家常菜谱</h1><p>应季食材，简单好做，把每一餐吃得温暖。</p></div><img src="assets/tomato-egg.jpg" alt="家常番茄炒蛋" /></section>
    <div class="section"><input class="search" id="recipeSearch" type="search" placeholder="搜索菜名或食材" aria-label="搜索菜谱" /></div>
    <div class="segmented">${categories.map(c => `<button class="chip ${state.recipeFilter === c ? 'active' : ''}" data-recipe-filter="${c}">${c}</button>`).join('')}</div>
    <section class="section">
      ${sectionHeader('◒', state.recipeFilter === '全部' ? '秋季推荐' : state.recipeFilter, '时令鲜味 · 家常好做')}
      <div class="card-grid" id="recipeGrid">${list.map(recipeCard).join('')}</div>
    </section>`;
}

function aiPage() {
  const messageHtml = state.messages.map(m => `<div class="bubble ${m.role}">${m.text}</div>`).join('');
  return `<div class="chat-layout">
    <section class="chat-panel">
      <div class="chat-head"><h1>小食 AI 助手</h1><p>我会结合时令、人数和家中食材给你建议</p><div class="quick-prompts"><button data-prompt="今天吃什么？">今天吃什么</button><button data-prompt="三人晚餐推荐">三人晚餐推荐</button><button data-prompt="用家里的食材做菜">现有食材做菜</button></div></div>
      <div class="messages" id="messages"><div class="bubble ai">你好，我是小食。现在是秋季，需要我帮你安排一顿简单又营养的晚餐吗？</div>${messageHtml}</div>
      <form class="chat-input" id="chatForm"><input id="chatText" autocomplete="off" placeholder="问问今晚吃什么…" aria-label="给AI助手发送消息" /><button aria-label="发送">➤</button></form>
    </section>
    <aside class="recommend-panel"><h2>为你推荐</h2><p>根据秋季时令与 3 人用餐生成</p>${recipeCard(recipes[0])}<button class="primary wide-cta" data-action="add-menu">加入今日菜单</button></aside>
  </div>`;
}

function profilePage() {
  return `<section class="profile-hero"><img class="avatar" src="assets/avatar.jpg" alt="小食同学头像" /><div><span class="eyebrow">我的食时</span><h1>小食同学</h1><p>顺应时令，认真吃饭</p></div></section>
    <div class="stats"><div class="stat"><strong>${state.favorites.size}</strong><span>收藏菜谱</span></div><div class="stat"><strong>28</strong><span>历史菜单</span></div><div class="stat"><strong>6</strong><span>我的食材</span></div><div class="stat"><strong>4</strong><span>饮食偏好</span></div></div>
    <section class="section ai-tip"><span class="tip-icon">▥</span><div><strong>本周饮食记录</strong><p>已安排 5 餐 · 常用食材：鸡蛋、番茄 · 饮食均衡</p></div></section>
    <section class="section"><h2>我的功能</h2><div class="menu-list">
      <button class="menu-item" data-action="favorites"><span>♥</span>我的收藏<small>收藏的菜谱 ›</small></button>
      <button class="menu-item" data-action="history"><span>◷</span>浏览历史<small>最近看过的菜谱 ›</small></button>
      <button class="menu-item" data-action="family"><span>♙</span>家庭人数设置<small>当前 3 人 ›</small></button>
      <button class="menu-item" data-action="preferences"><span>◒</span>忌口与偏好<small>清淡、少糖 ›</small></button>
      <button class="menu-item" data-action="settings"><span>●</span>提醒设置<small>用餐与时令提醒 ›</small></button>
    </div></section>`;
}

const pages = { home: homePage, foods: foodsPage, recipes: recipesPage, ai: aiPage, profile: profilePage };

function render(focus = false) {
  if (!pages[state.route]) state.route = 'home';
  view.innerHTML = pages[state.route]();
  updateNav();
  document.title = `${navItems.find(n => n[0] === state.route)?.[2] || '首页'} · 食时`;
  if (focus) view.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function openRecipe(id) {
  const r = recipes.find(recipe => recipe.id === id) || recipes[0];
  document.querySelector('#detailContent').innerHTML = `<button class="sheet-close" data-close="detail" aria-label="关闭">×</button><div class="detail-hero"><img src="${r.image}" alt="${r.name}" /></div><div class="detail-body"><span class="eyebrow">秋季时令 · 家常好味</span><h1>${r.name}</h1><p>${r.desc}。选用当季食材，味道清甜自然，适合一家人慢慢享用。</p><div class="tags">${r.tags.map((t,i) => `<span class="tag ${i === 0 ? 'warm' : ''}">${t}</span>`).join('')}</div><div class="detail-facts"><div class="fact">◷<br /><strong>${r.time}</strong></div><div class="fact">♙<br /><strong>${r.people}</strong></div><div class="fact">♨<br /><strong>简单</strong></div></div><h2>所需食材</h2><div class="ingredient-row"><span class="ingredient">莲藕 1节</span><span class="ingredient">排骨 500克</span><span class="ingredient">胡萝卜 1根</span><span class="ingredient">姜 3片</span><span class="ingredient">葱 2根</span></div><h2>做法步骤</h2><ol class="steps"><li>排骨冷水下锅焯水，煮开后捞出冲洗干净。</li><li>莲藕和胡萝卜切块，姜切片，葱切段备用。</li><li>食材放入锅中，加清水，大火煮开后小火慢炖。</li><li>加盐调味，撒上葱花即可享用。</li></ol></div><div class="dialog-actions"><button class="secondary" data-action="add-menu">加入今日菜单</button><button class="primary" data-action="open-shopping">加入购物清单</button></div>`;
  detailDialog.showModal();
}

function openShopping() {
  const groups = ['蔬菜', '肉蛋', '调味'];
  const checked = state.shopping.filter(i => i[2]).length;
  document.querySelector('#shoppingContent').innerHTML = `<button class="sheet-close" data-close="shopping" aria-label="关闭">×</button><div class="shopping-head"><span class="eyebrow">本周准备</span><h2>购物清单</h2><p>已勾选 ${checked} / ${state.shopping.length} 项</p></div><div class="shopping-list">${groups.map(group => `<section class="shopping-group"><h3>${group}</h3>${state.shopping.map((item,index) => ({ item, index })).filter(x => x.item[3] === group).map(({item,index}) => `<label class="check-row ${item[2] ? 'checked' : ''}"><input type="checkbox" data-shopping="${index}" ${item[2] ? 'checked' : ''} /><span>${item[0]}</span><small>${item[1]}</small></label>`).join('')}</section>`).join('')}<button class="primary wide-cta" data-action="complete-shopping">完成采购</button></div>`;
  if (detailDialog.open) detailDialog.close();
  shoppingDialog.showModal();
}

let toastTimer;
function toast(message) {
  const el = document.querySelector('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 1800);
}

function routeTo(route) {
  state.route = route;
  history.replaceState(null, '', `#${route}`);
  render(true);
}

document.addEventListener('click', event => {
  const route = event.target.closest('[data-route]')?.dataset.route;
  if (route) return routeTo(route);
  const recipe = event.target.closest('[data-recipe]')?.dataset.recipe;
  if (recipe) return openRecipe(recipe);
  const favorite = event.target.closest('[data-favorite]')?.dataset.favorite;
  if (favorite) {
    event.stopPropagation();
    state.favorites.has(favorite) ? state.favorites.delete(favorite) : state.favorites.add(favorite);
    render(); toast(state.favorites.has(favorite) ? '已加入收藏' : '已取消收藏'); return;
  }
  const foodFilter = event.target.closest('[data-food-filter]')?.dataset.foodFilter;
  if (foodFilter) { state.foodFilter = foodFilter; render(); return; }
  const recipeFilter = event.target.closest('[data-recipe-filter]')?.dataset.recipeFilter;
  if (recipeFilter) { state.recipeFilter = recipeFilter; render(); return; }
  const prompt = event.target.closest('[data-prompt]')?.dataset.prompt;
  if (prompt) return sendMessage(prompt);
  const close = event.target.closest('[data-close]')?.dataset.close;
  if (close === 'detail') detailDialog.close();
  if (close === 'shopping') shoppingDialog.close();
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (!action) return;
  if (action === 'open-shopping') return openShopping();
  if (action === 'foods' || action === 'recipes') return routeTo(action);
  if (action === 'cook-with-foods') { routeTo('ai'); setTimeout(() => sendMessage('用家里的食材做菜'), 40); return; }
  if (action === 'today-menu') return toast('今日菜单：莲藕排骨汤、番茄炒蛋、清炒白菜');
  if (action === 'add-menu') return toast('已加入今日菜单');
  if (action === 'complete-shopping') { shoppingDialog.close(); return toast('采购清单已完成'); }
  if (action === 'favorites') return toast(`你收藏了 ${state.favorites.size} 道菜谱`);
  if (action === 'history') return toast('最近看过：莲藕排骨汤、番茄炒蛋');
  if (action === 'family') return toast('家庭人数：3 人');
  if (action === 'preferences') return toast('偏好：家常、清淡、少糖');
  if (action === 'settings') return toast('提醒设置已开启');
});

document.addEventListener('change', event => {
  const index = event.target.dataset.shopping;
  if (index !== undefined) { state.shopping[Number(index)][2] = event.target.checked; openShoppingRefresh(); }
});

function openShoppingRefresh() {
  shoppingDialog.close();
  openShopping();
}

document.addEventListener('input', event => {
  if (event.target.id !== 'recipeSearch') return;
  const q = event.target.value.trim().toLowerCase();
  const filtered = recipes.filter(r => `${r.name}${r.desc}${r.tags.join('')}`.toLowerCase().includes(q));
  document.querySelector('#recipeGrid').innerHTML = filtered.length ? filtered.map(recipeCard).join('') : '<div class="empty">没有找到匹配的菜谱</div>';
});

document.addEventListener('submit', event => {
  if (event.target.id !== 'chatForm') return;
  event.preventDefault();
  const input = document.querySelector('#chatText');
  if (input.value.trim()) sendMessage(input.value.trim());
});

function sendMessage(text) {
  state.messages.push({ role: 'user', text });
  const answer = text.includes('食材') ? '你家现有的番茄、鸡蛋和白菜很适合做番茄炒蛋与清炒白菜，再搭配莲藕排骨汤，就是一顿营养均衡的三人晚餐。' : '结合杭州秋季时令，我推荐莲藕排骨汤、番茄炒蛋和清炒白菜。荤素搭配，味道温和，适合 2–3 人。';
  state.messages.push({ role: 'ai', text: `${answer}<br><button class="text-button" data-recipe="soup">查看结构化菜谱卡片 →</button>` });
  render();
  requestAnimationFrame(() => document.querySelector('#messages')?.scrollTo({ top: 9999, behavior: 'smooth' }));
}

window.addEventListener('hashchange', () => { state.route = location.hash.slice(1) || 'home'; render(true); });
render();
