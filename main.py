import threading
import time
import datetime
import os
import socket
import ssl
import json
import concurrent.futures
from pathlib import Path
import shutil
import sqlite3
import webbrowser
import sys
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import uvicorn

# ===================== 路径兼容 PyInstaller =====================
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)  # PyInstaller 临时路径
    EXE_DIR = Path(sys.executable).parent  # exe 所在目录
else:
    BASE_DIR = Path(__file__).parent
    EXE_DIR = BASE_DIR

DB_PATH = EXE_DIR / "host_config.db"
TEMPLATES_PATH = BASE_DIR / "templates"

# ===================== 初始化 =====================
app = FastAPI()
# 冻结后需要显式指定绝对路径，避免 uvicorn 找不到模板目录
templates = Jinja2Templates(directory=str(TEMPLATES_PATH))

if os.name == "nt":
    HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
else:
    HOSTS_PATH = Path("/etc/hosts")

# 默认 IP 列表（每行一个）
DEFAULT_IPS = [
    "119.28.13.121",
    "154.40.44.47",
    "101.32.183.34",
    "43.128.3.53",
    "104.18.22.110",
    "104.26.4.98",
    "104.18.39.102",
    "104.21.34.55",
    "172.67.202.131",
    "104.16.249.45",
    "208.103.161.2",
]

# 默认域名列表
DEFAULT_DOMAINS = [
    {"name": "www.notion.so", "checked": True, "desc": "Notion 主站网页访问入口"},
    {"name": "msgstore.www.notion.so", "checked": True, "desc": "消息/通知/同步服务"},
    {"name": "api.pgncs.notion.so", "checked": False, "desc": "Notion API 接口"},
    {"name": "exp.notion.so", "checked": False, "desc": "实验 / Beta 功能"},
    {"name": "s3.us-west-2.amazonaws.com", "checked": False, "desc": "图片/附件/导出文件存储"},
]

# 默认检测间隔 0
DEFAULT_INTERVAL = 0

# ===================== 数据库 =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
                    ts TEXT,
                    message TEXT
                )""")
    conn.commit()
    conn.close()

def set_config(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def get_config(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO logs (ts,message) VALUES (?,?)", (ts, msg))
    conn.commit()
    conn.close()
    print(f"[{ts}] {msg}")

def get_logs(limit=200):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ts,message FROM logs ORDER BY ts DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [f"[{ts}] {msg}" for ts, msg in reversed(rows)]

# ===================== 权限检测 =====================
def has_admin_privilege():
    if os.name == "nt":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        return os.geteuid() == 0

# ===================== HTTPS检测 =====================
def https_check_and_latency(ip, domain, timeout=3):
    context = ssl.create_default_context()
    start = time.perf_counter()
    try:
        with socket.create_connection((ip, 443), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                req = f"HEAD / HTTP/1.1\r\nHost: {domain}\r\nConnection: close\r\n\r\n"
                ssock.sendall(req.encode())
                ssock.recv(1024)
        latency = (time.perf_counter() - start) * 1000
        return True, latency
    except:
        return False, None

def test_ip_for_domain(ip, domain, timeout=3):
    ok, latency = https_check_and_latency(ip, domain, timeout=timeout)
    return latency if ok else None

def _normalize_lines(text: str):
    lines = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s:
            lines.append(s)
    # 去重但保留顺序
    seen = set()
    out = []
    for x in lines:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

def pick_fastest_ip_per_domain(ips, domains, timeout=3, max_workers=24):
    """
    对每个 domain 单独测速，返回：
    - fastest: {domain: (ip, latency_ms)}   (仅包含测速成功的域名)
    - domain_latencies: {domain: {ip: latency_ms}}
    """
    ips = [ip.strip() for ip in ips if ip and ip.strip()]
    domains = [d.strip() for d in domains if d and d.strip()]
    domain_latencies = {d: {} for d in domains}
    fastest = {}

    if not ips or not domains:
        return fastest, domain_latencies

    # 线程池并发测速，避免串行太慢
    workers = max(4, min(max_workers, len(ips) * len(domains)))

    def _task(ip, domain):
        latency = test_ip_for_domain(ip, domain, timeout=timeout)
        return domain, ip, latency

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_task, ip, domain) for domain in domains for ip in ips]
        for fut in concurrent.futures.as_completed(futures):
            domain, ip, latency = fut.result()
            if latency is None:
                continue
            domain_latencies.setdefault(domain, {})[ip] = latency

    for domain, ip_map in domain_latencies.items():
        if not ip_map:
            continue
        best_ip = min(ip_map, key=ip_map.get)
        fastest[domain] = (best_ip, ip_map[best_ip])

    return fastest, domain_latencies

# ===================== hosts更新 =====================
def backup_hosts():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = HOSTS_PATH.with_name(f"{HOSTS_PATH.name}.bak_{ts}")
    shutil.copy(HOSTS_PATH, backup)
    log(f"hosts 已备份: {backup}")

def update_hosts(domain_to_ip):
    content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    new_lines = []
    domain_set = set(domain_to_ip.keys())
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# notion auto update"):
            continue
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        parts = stripped.split()
        # hosts 可能一行多个域名：127.0.0.1 a b c
        if len(parts) >= 2 and any(p in domain_set for p in parts[1:]):
            continue
        new_lines.append(line)
    new_lines.append("")
    new_lines.append(f"# notion auto update {datetime.datetime.now()}")
    for domain, ip in domain_to_ip.items():
        new_lines.append(f"{ip} {domain}")
    HOSTS_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    log(f"hosts 已更新, 域名数: {len(domain_to_ip)}")

# ===================== 执行检测更新 =====================
def run_check_and_update(ips=None, domains=None):
    if ips is None:
        ips = _normalize_lines(get_config("ips", "\n".join(DEFAULT_IPS)))
    else:
        ips = _normalize_lines("\n".join(ips) if isinstance(ips, (list, tuple)) else str(ips))
    if domains is None:
        # 只从配置里读取“已勾选”的域名；首次启动若无配置，则用默认勾选项
        raw = get_config("domains", None)
        if raw is None:
            domains = [d["name"] for d in DEFAULT_DOMAINS if d.get("checked")]
        else:
            domains = _normalize_lines(raw)
    else:
        domains = _normalize_lines("\n".join(domains) if isinstance(domains, (list, tuple)) else str(domains))
    if not has_admin_privilege():
        log("❌ 请以管理员/ root 权限运行")
        return None

    if not ips:
        log("❌ IP 列表为空")
        return None
    if not domains:
        log("❌ 未选择任何域名")
        return None

    # 读取上次结果，作为某些域名测速失败时的兜底
    last_domain_ips_raw = get_config("last_domain_ips", "{}")
    try:
        last_domain_ips = json.loads(last_domain_ips_raw) if last_domain_ips_raw else {}
        if not isinstance(last_domain_ips, dict):
            last_domain_ips = {}
    except Exception:
        last_domain_ips = {}

    fastest, domain_latencies = pick_fastest_ip_per_domain(ips, domains)

    domain_to_ip = {}
    for domain in domains:
        if domain in fastest:
            ip, latency = fastest[domain]
            domain_to_ip[domain] = ip
            log(f"域名 {domain} 最快 IP: {ip} ({latency:.1f} ms)")
        else:
            fallback = last_domain_ips.get(domain)
            if fallback:
                domain_to_ip[domain] = fallback
                log(f"⚠️ 域名 {domain} 本次无可用 IP，沿用上次: {fallback}")
            else:
                log(f"❌ 域名 {domain} 本次无可用 IP，且无历史可用值")

    if not domain_to_ip:
        log("❌ 没有任何域名找到可用 IP")
        return None

    # 用主域名（优先 www.notion.so）作为“当前 IP”展示
    if "www.notion.so" in domain_to_ip:
        fastest_ip = domain_to_ip["www.notion.so"]
    else:
        fastest_ip = next(iter(domain_to_ip.values()))

    backup_hosts()
    update_hosts(domain_to_ip)
    set_config("last_ip", fastest_ip)
    set_config("last_run", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    set_config("last_domain_ips", json.dumps(domain_to_ip, ensure_ascii=False))
    return domain_to_ip

# ===================== FastAPI接口 =====================
@app.on_event("startup")
def startup_event():
    init_db()
    # 自动任务线程
    def auto_task():
        while True:
            try:
                interval = int(get_config("interval", DEFAULT_INTERVAL))
                if interval <= 0:
                    time.sleep(5)
                    continue
                time.sleep(interval)
                log("自动任务触发")
                run_check_and_update()
            except Exception as e:
                log(f"自动任务异常: {e}")
    threading.Thread(target=auto_task, daemon=True).start()

    # 自动打开浏览器
    def open_browser():
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:5000")
    threading.Thread(target=open_browser).start()

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    ip_config = get_config("ips", "\n".join(DEFAULT_IPS)).splitlines()

    raw = get_config("domains", None)
    if raw is None:
        selected = set([d["name"] for d in DEFAULT_DOMAINS if d.get("checked")])
    else:
        selected = set(_normalize_lines(raw))

    domain_config = []
    default_names = set()
    for d in DEFAULT_DOMAINS:
        default_names.add(d["name"])
        domain_config.append({
            "name": d["name"],
            "checked": d["name"] in selected,
            "desc": d.get("desc", ""),
            "is_custom": False,
        })

    # 将用户自定义域名也渲染到页面（从配置中的“已勾选域名”推导）
    for name in _normalize_lines("\n".join(sorted(selected))):
        if name in default_names:
            continue
        domain_config.append({
            "name": name,
            "checked": True,
            "desc": "自定义域名",
            "is_custom": True,
        })

    # 读取每域名对应 IP 的结果用于展示
    last_domain_ips_raw = get_config("last_domain_ips", "{}")
    try:
        last_domain_ips = json.loads(last_domain_ips_raw) if last_domain_ips_raw else {}
        if not isinstance(last_domain_ips, dict):
            last_domain_ips = {}
    except Exception:
        last_domain_ips = {}
    status = {
        "last_ip": get_config("last_ip",""),
        "last_run": get_config("last_run",""),
        "logs": get_logs(200),
        "domain_ips": last_domain_ips,
    }
    return templates.TemplateResponse("index.html", {"request": request, "ips": ip_config, "domains": domain_config, "status": status, "interval": get_config("interval", DEFAULT_INTERVAL)})

@app.post("/save_config")
def save_config(ips: str = Form(...), domains: str = Form(...), interval: int = Form(...)):
    set_config("ips", ips.strip())
    # 只保存勾选域名
    selected_domains = "\n".join(_normalize_lines(domains))
    set_config("domains", selected_domains)
    set_config("interval", interval)
    return JSONResponse({"msg":"配置保存成功"})

@app.post("/run_now")
def run_now():
    fastest_ip = run_check_and_update()
    # 兼容旧字段 fastest_ip（用于提示），同时返回每域名结果 domain_ips
    if isinstance(fastest_ip, dict):
        main_ip = fastest_ip.get("www.notion.so") or next(iter(fastest_ip.values()), None)
        return JSONResponse({"fastest_ip": main_ip, "domain_ips": fastest_ip, "logs": get_logs(200)})
    return JSONResponse({"fastest_ip": fastest_ip, "domain_ips": {}, "logs": get_logs(200)})

if __name__ == "__main__":
    uvicorn.run(
        app,              # 直接传递实例，避免打包后找不到 main 模块
        host="0.0.0.0",
        port=5000,
        reload=False,     # 打包 exe 不要 reload
        log_config=None   # 禁用默认 logging 配置
    )
