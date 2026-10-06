#!/usr/bin/env bash
#
# 食时 · 服务器一键部署（幂等，重复跑没问题）
#
# 用法：
#   sudo bash deploy/deploy.sh                # 正常部署 / 更新
#   sudo bash deploy/deploy.sh --reload-data  # 强制重新导入菜谱内容表
#   sudo bash deploy/deploy.sh --no-web       # 只更新后端（跳过前端产物）
#   sudo bash deploy/deploy.sh --web-from-release  # 前端强制用 CI 的 Release 产物
#
# 做完这些事：
#   1. 检查/生成 back/.env（并提醒你改 SECRET_KEY、填 AI_API_KEY）
#   2. 建虚拟环境 + 装依赖
#   3. 建库 + 首次导入清洗好的内容数据（ingredients / dishes / 时令表）
#   4. 注册并启动 systemd 服务 shishi-backend
#   5. 前端产物 → /opt/web（优先用仓库自带的 build/web，其次下 CI 的 Release）
#   6. 装 nginx 配置（静态站 + /api 反代）并重载
#   7. 自检

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACK_DIR="$REPO_DIR/back"
SQL_DIR="$REPO_DIR/sql/cleaned_v2"
WEB_DIR="/opt/web"
SERVICE_NAME="shishi-backend"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_CONF="/etc/nginx/conf.d/shishi.conf"
WEB_RELEASE_URL="https://github.com/aiczz/test/releases/download/web-latest/web-build.tar.gz"

RELOAD_DATA=0
DO_WEB=1
WEB_FROM_RELEASE=0
for arg in "$@"; do
  case "$arg" in
    --reload-data)       RELOAD_DATA=1 ;;
    --no-web)            DO_WEB=0 ;;
    --web-from-release)  WEB_FROM_RELEASE=1 ;;
    -h|--help)           sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg"; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 跑：sudo bash deploy/deploy.sh"
[ -d "$BACK_DIR" ] || die "找不到 $BACK_DIR —— 这个脚本要在仓库的 deploy/ 目录下跑"

# ---------------------------------------------------------------------
say "1/7 配置 back/.env"
# ---------------------------------------------------------------------
if [ ! -f "$BACK_DIR/.env" ]; then
  cp "$BACK_DIR/.env.example" "$BACK_DIR/.env"
  echo "  已从 .env.example 生成 back/.env"
fi

if grep -q '^SECRET_KEY=dev-only-change-me' "$BACK_DIR/.env"; then
  NEW_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  # 用 python 改，避免 sed 把值里的特殊字符吃坏
  python3 - "$BACK_DIR/.env" "$NEW_SECRET" <<'PY'
import sys, pathlib
path, secret = pathlib.Path(sys.argv[1]), sys.argv[2]
lines = []
for line in path.read_text(encoding="utf-8").splitlines():
    lines.append(f"SECRET_KEY={secret}" if line.startswith("SECRET_KEY=") else line)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
  echo "  已把 SECRET_KEY 换成随机值（原来的默认值能被人伪造管理员登录）"
fi

if ! grep -qE '^AI_API_KEY=.+' "$BACK_DIR/.env"; then
  warn "back/.env 里 AI_API_KEY 是空的。"
  warn "  → 服务照样能跑（AI 自动退回确定性算法），但首页推荐和 AI 助手不会有 AI 润色。"
  warn "  → 要开 AI：向项目负责人索取 key，填进 $BACK_DIR/.env 的 AI_API_KEY 后重启服务。"
fi

# ---------------------------------------------------------------------
say "2/7 准备 Python 环境"
# ---------------------------------------------------------------------
PY="$BACK_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  if ! python3 -m venv "$BACK_DIR/.venv" 2>/dev/null; then
    warn "python3 -m venv 失败，尝试安装 python3-venv"
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update -qq && apt-get install -y -qq python3-venv
    elif command -v yum >/dev/null 2>&1; then
      yum install -y python3-virtualenv || true
    fi
    python3 -m venv "$BACK_DIR/.venv" || die "建虚拟环境失败，请先装 python3-venv"
  fi
  echo "  已创建虚拟环境 $BACK_DIR/.venv"
fi

"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r "$BACK_DIR/requirements.txt"
echo "  依赖已就绪（$("$PY" --version)）"

# ---------------------------------------------------------------------
say "3/7 准备数据库与内容数据"
# ---------------------------------------------------------------------
DB_PATH="$BACK_DIR/shishi.db"
"$PY" - <<PY
import sys
sys.path.insert(0, "$BACK_DIR")
from app.core.database import create_db_and_tables
create_db_and_tables()
print("  表结构已就绪")
PY

content_rows() {
  "$PY" - <<PY
import sqlite3
con = sqlite3.connect("$DB_PATH")
try:
    print(con.execute("SELECT COUNT(*) FROM dishes").fetchone()[0])
except sqlite3.OperationalError:
    print(0)
con.close()
PY
}

ROWS="$(content_rows)"
if [ "$RELOAD_DATA" -eq 1 ] || [ "$ROWS" -lt 1000 ]; then
  echo "  当前 dishes 行数=$ROWS，导入清洗好的内容数据（约 1 分钟）..."
  "$PY" "$SQL_DIR/load_to_sqlite.py" --db "$DB_PATH"
  echo "  导入后 dishes 行数=$(content_rows)"
else
  echo "  内容数据已存在（dishes=$ROWS 行），跳过导入。强制重导：--reload-data"
fi

# ---------------------------------------------------------------------
say "4/7 注册 systemd 服务"
# ---------------------------------------------------------------------
sed "s#^ExecStart=.*#ExecStart=$PY -m uvicorn app.main:app --host 127.0.0.1 --port 8000#" \
  "$REPO_DIR/deploy/${SERVICE_NAME}.service" > "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl restart "$SERVICE_NAME"
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "  $SERVICE_NAME 已启动"
else
  warn "$SERVICE_NAME 没起来，日志："
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
  die "后端启动失败"
fi

# ---------------------------------------------------------------------
say "5/7 前端产物"
# ---------------------------------------------------------------------
# 两个来源，优先用本地已有的（不依赖网络）：
#   ① 仓库里就带着构建好的 front/mealmind/build/web
#      —— 适用于「直接把整个文件夹拷给运维」这种交付方式，
#         服务器上不需要 Flutter、也不需要联网下 Release
#   ② 从 GitHub Release 下载（CI 构建的）
#      —— 适用于「push 到 GitHub → 服务器 git pull」这种交付方式
LOCAL_WEB="$REPO_DIR/front/mealmind/build/web"
if [ "$DO_WEB" -eq 0 ]; then
  echo "  --no-web：跳过"
else
  mkdir -p "$WEB_DIR"
  if [ "$WEB_FROM_RELEASE" -eq 0 ] && [ -f "$LOCAL_WEB/index.html" ]; then
    find "$WEB_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    cp -a "$LOCAL_WEB/." "$WEB_DIR/"
    echo "  已用仓库里自带的产物更新 $WEB_DIR（$(find "$WEB_DIR" -type f | wc -l) 个文件）"
    echo "  想改用 CI 的 Release 产物：--web-from-release"
  else
    TMP_TGZ="$(mktemp -d)/web-build.tar.gz"
    if curl -fsSL --connect-timeout 20 -o "$TMP_TGZ" "$WEB_RELEASE_URL"; then
      find "$WEB_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
      tar -xzf "$TMP_TGZ" -C "$WEB_DIR"
      echo "  已从 GitHub Release 更新 $WEB_DIR（$(find "$WEB_DIR" -type f | wc -l) 个文件）"
    else
      warn "下载前端产物失败（网络？仓库还没有 Release？）"
      if [ -f "$WEB_DIR/index.html" ]; then
        warn "  保留 $WEB_DIR 里已有的旧产物，继续。"
      else
        die "  $WEB_DIR 是空的，站点会是白屏。\
请把本地 flutter build web 的产物放到 $LOCAL_WEB 再跑，或等 CI 出 Release。"
      fi
    fi
  fi
fi

# ---------------------------------------------------------------------
say "6/7 配置 nginx"
# ---------------------------------------------------------------------
if ! command -v nginx >/dev/null 2>&1; then
  warn "没装 nginx，尝试安装"
  if command -v apt-get >/dev/null 2>&1; then apt-get install -y -qq nginx
  elif command -v yum >/dev/null 2>&1; then yum install -y nginx
  else die "装不了 nginx，请手动装"; fi
fi

install -D -m 644 "$REPO_DIR/deploy/nginx-shishi.conf" "$NGINX_CONF"

# 发行版自带的默认站点会抢 80 端口（它是 default_server），关掉它
for f in /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf; do
  [ -e "$f" ] && mv "$f" "${f}.disabled-by-shishi" && echo "  已停用冲突的默认站点：$f"
done

nginx -t || die "nginx 配置有问题，看上面的报错"
systemctl reload nginx 2>/dev/null || systemctl restart nginx
echo "  nginx 已重载"

# ---------------------------------------------------------------------
say "7/7 自检"
# ---------------------------------------------------------------------
sleep 1
printf '  后端直连  : '
curl -fsS --max-time 10 http://127.0.0.1:8000/api/health || warn "后端没响应"
printf '\n  经 nginx  : '
curl -fsS --max-time 10 http://127.0.0.1/api/health || warn "nginx 反代没通"
printf '\n  首页数据  : '
curl -fsS --max-time 60 'http://127.0.0.1/api/home?city=%E6%9D%AD%E5%B7%9E' \
  | head -c 120 || warn "首页接口没响应"
printf '\n'

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<EOF

────────────────────────────────────────────────────────
部署完成 ✅

  站点：      http://${IP:-<服务器IP>}/
  接口文档：  http://${IP:-<服务器IP>}/docs
  演示账号：  demo / shishi2026

  后端状态：  systemctl status ${SERVICE_NAME}
  实时日志：  journalctl -u ${SERVICE_NAME} -f
  验收脚本：  $PY $BACK_DIR/scripts/verify_ai_features.py --base http://127.0.0.1

还没做的两件事（按需）：
  1. 换 SECRET_KEY —— 脚本已自动换过；若你手工改过 .env 请确认它不是默认值
  2. 填 AI_API_KEY —— 填完 sudo systemctl restart ${SERVICE_NAME}
  3. 上 HTTPS   —— sudo certbot --nginx -d 你的域名（不用重新构建前端）
────────────────────────────────────────────────────────
EOF
