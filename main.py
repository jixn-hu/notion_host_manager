import threading
import time
import datetime
import os
import socket
import ssl
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
    {"name": "www.notion.so", "checked": True},
    {"name": "msgstore.www.notion.so", "checked": True},
    {"name": "api.pgncs.notion.so", "checked": False},
    {"name": "exp.notion.so", "checked": False},
    {"name": "s3.us-west-2.amazonaws.com", "checked": False},
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

def test_ip(ip, domains):
    latencies = []
    for domain in domains:
        ok, latency = https_check_and_latency(ip, domain)
        if not ok:
            return None
        latencies.append(latency)
    return sum(latencies) / len(latencies)

# ===================== hosts更新 =====================
def backup_hosts():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = HOSTS_PATH.with_name(f"{HOSTS_PATH.name}.bak_{ts}")
    shutil.copy(HOSTS_PATH, backup)
    log(f"hosts 已备份: {backup}")

def update_hosts(ip, domains):
    content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    new_lines = []
    domain_set = set(domains)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# notion auto update"):
            continue
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        parts = stripped.split()
        if len(parts) >= 2 and parts[1] in domain_set:
            continue
        new_lines.append(line)
    new_lines.append("")
    new_lines.append(f"# notion auto update {datetime.datetime.now()}")
    for domain in domains:
        new_lines.append(f"{ip} {domain}")
    HOSTS_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    log(f"hosts 已更新, IP: {ip}")

# ===================== 执行检测更新 =====================
def run_check_and_update(ips=None, domains=None):
    if ips is None:
        ips = get_config("ips", "\n".join(DEFAULT_IPS)).splitlines()
    if domains is None:
        domains = [d for d in get_config("domains", "\n".join([d['name'] for d in DEFAULT_DOMAINS])).splitlines() if d.strip()]
    if not has_admin_privilege():
        log("❌ 请以管理员/ root 权限运行")
        return None
    results = {}
    for ip in ips:
        avg = test_ip(ip, domains)
        if avg is not None:
            results[ip] = avg
            log(f"IP {ip} 可用, 平均延迟 {avg:.1f} ms")
        else:
            log(f"IP {ip} 不可用")
    if not results:
        log("❌ 没有可用 IP")
        return None
    fastest_ip = min(results, key=results.get)
    backup_hosts()
    update_hosts(fastest_ip, domains)
    set_config("last_ip", fastest_ip)
    set_config("last_run", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return fastest_ip

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
    domain_config_raw = get_config("domains", "\n".join([d['name'] for d in DEFAULT_DOMAINS])).splitlines()
    domain_config = []
    for d in DEFAULT_DOMAINS:
        domain_config.append({
            "name": d['name'],
            "checked": d['name'] in domain_config_raw or d['checked']
        })
    status = {
        "last_ip": get_config("last_ip",""),
        "last_run": get_config("last_run",""),
        "logs": get_logs(200)
    }
    return templates.TemplateResponse("index.html", {"request": request, "ips": ip_config, "domains": domain_config, "status": status, "interval": get_config("interval", DEFAULT_INTERVAL)})

@app.post("/save_config")
def save_config(ips: str = Form(...), domains: str = Form(...), interval: int = Form(...)):
    set_config("ips", ips.strip())
    # 只保存勾选域名
    selected_domains = "\n".join([d.strip() for d in domains.strip().splitlines() if d.strip()])
    set_config("domains", selected_domains)
    set_config("interval", interval)
    return JSONResponse({"msg":"配置保存成功"})

@app.post("/run_now")
def run_now():
    fastest_ip = run_check_and_update()
    return JSONResponse({"fastest_ip": fastest_ip, "logs": get_logs(200)})

if __name__ == "__main__":
    uvicorn.run(
        app,              # 直接传递实例，避免打包后找不到 main 模块
        host="0.0.0.0",
        port=5000,
        reload=False,     # 打包 exe 不要 reload
        log_config=None   # 禁用默认 logging 配置
    )
