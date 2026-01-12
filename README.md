
# 🚀 Notion Hosts 管理

![img.png](https://github.com/jixn-hu/notion_host_manager/blob/main/img/img.png)


一个 **专注于 Notion Hosts 自动优化的本地管理工具**
支持 **延迟测速选最快 IP、可视化配置、自动/手动更新 hosts、FastAPI + SQLite + Web UI**，并可 **打包为 Windows 单文件 exe**。

> 目标：
> **更快、更稳定地访问 Notion（尤其在国内网络环境）**
> 无需手动折腾 hosts，一次配置，长期使用。

---

## ✨ 功能特性

### 🧠 核心能力

* ✅ **多 IP 延迟测速**，自动选择最快 IP
* ✅ **按域名精细控制**，支持勾选启用
* ✅ **一键写入 / 更新 hosts**
* ✅ **自动备份 hosts**
* ✅ **自动删除 Notion Auto Update 相关 hosts 记录**
* ✅ **支持手动触发 & 定时检测**
* ✅ **配置持久化（SQLite）**
* ✅ **启动自动打开 Web 管理界面**

---

### 🌐 默认支持的 Notion 域名（可勾选）

| 域名                           | 用途说明                    |
| ---------------------------- | ----------------------- |
| `www.notion.so`              | Notion 主站网页访问入口（默认启用）   |
| `msgstore.www.notion.so`     | Notion 消息/通知/同步服务（默认启用） |
| `api.pgncs.notion.so`        | Notion API 接口（可选）       |
| `exp.notion.so`              | Notion 实验 / Beta 功能（可选）     |
| `s3.us-west-2.amazonaws.com` | Notion 图片、附件、导出文件存储（可选）     |

---

### 🌍 默认 IP 列表（可自由编辑）

> **一行一个 IP**

```text
119.28.13.121
154.40.44.47
101.32.183.34
43.128.3.53
104.18.22.110
104.26.4.98
104.18.39.102
104.21.34.55
172.67.202.131
104.16.249.45
208.103.161.2
```

* 包含 **腾讯云 / 海外节点 / Cloudflare CDN**
* 程序会自动测速并选最快 IP

---

## 🖥 Web 管理界面（UI）

* 🎨 **极简优雅风格**
* 🧱 卡片化布局 + 微阴影
* 📱 **响应式设计**（手机 / 平板 / 桌面）
* 🖱 大按钮，适合触控
* 🧾 域名用途清晰标注
* 📜 实时日志展示

> UI 使用 **Tailwind CSS CDN**，无图片依赖，纯 CSS 实现。

---

## ⚙️ 技术栈

| 层级     | 技术                      |
| ------ | ----------------------- |
| 后端     | FastAPI                 |
| Web 服务 | Uvicorn                 |
| 前端     | HTML + Tailwind CSS     |
| 配置存储   | SQLite                  |
| 延迟测速   | Socket / TCP connect    |
| 系统支持   | Windows / Linux / macOS |
| 打包     | PyInstaller             |

---

## 📁 项目结构

```text
notion_host_manager/
├─ main.py                # FastAPI 主程序
├─ templates/
│  └─ index.html          # Web UI
├─ host_config.db         # SQLite（自动生成）
├─ README.md
```

---

## ▶️ 本地运行（Python）

### 1️⃣ 安装依赖

```bash
pip install fastapi uvicorn
```

### 2️⃣ 启动

```bash
python main.py
```

* 启动后会 **自动打开浏览器**
* 默认地址：`http://127.0.0.1:5000`

⚠️ **修改 hosts 需要管理员权限**

* Windows：以管理员身份运行
* Linux / macOS：使用 `sudo`

---

## ⏱ 自动检测说明

* **检测间隔默认 = 0**

  * 表示 **不自动检测**
* 设置为 `>0` 秒后：

  * 程序会按间隔自动测速并更新 hosts

---

✅ 已处理：

* `uvicorn logging isatty` 问题
* `--noconsole` 无控制台模式
* 模板路径兼容 PyInstaller

---

## 🛡 安全说明

* 仅修改本机 `hosts` 文件
* 所有配置 **只存储在本地 SQLite**
* 不联网、不上传任何数据
* hosts 修改前自动备份

---

## 🎯 使用场景

* 国内访问 Notion 慢 / 不稳定
* 不想手动折腾 hosts
* 希望可视化管理 + 自动优化
* 需要一个 **长期稳定方案**

---

## 📌 项目定位

> **一个“装上就不用管”的 Notion 网络优化工具**

不做代理
不翻墙
只做 **DNS / Hosts 层面的最优解**

---

如果你后续想加：

* 🌙 深色模式
* 📊 IP 历史延迟统计
* 🔔 更新通知
* 🧩 插件化域名支持

我可以在这个项目基础上继续帮你演进。
