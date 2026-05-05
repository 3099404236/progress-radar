# ProgressRadar v2

桌面客户端 · 粘贴 → AI 自动归类 · 阶段演化 · 非线性行进 · 周期循环 · 深色主题

## 首次配置

1. 装依赖（需要 Python 3.10+）：

```powershell
pip install -r requirements.txt
```

2. 配置 DeepSeek API key（二选一）：

```powershell
# 方式 A：环境变量
setx DEEPSEEK_API_KEY "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 方式 B：复制 secrets.example.py 为 secrets.local.py，把 key 填进去
copy secrets.example.py secrets.local.py
notepad secrets.local.py
```

3. 一次性把启动脚本和桌面快捷方式生成出来：

```powershell
python install_shortcut.py
```

## 启动

```powershell
python main.py
```

启动后程序常驻系统托盘：

- 托盘图标 **左键** → 打开 Dashboard
- 托盘图标 **右键** → 菜单（Dashboard / 快速粘贴 / 退出）
- **Ctrl + Shift + P** → 全局热键唤出快速粘贴窗口
- 关闭窗口 → 隐藏到托盘（不退出）
- 在快速粘贴窗里 **Esc** 也能隐藏

## 开机自启

```powershell
python autostart.py register     # 注册
python autostart.py status        # 查看状态
python autostart.py unregister   # 取消
```

## 周报

```powershell
python weekly_report.py
```

或在 Dashboard 右上角点 **生成周报**。

## 关键差异（vs v1）

- **桌面客户端**：原生窗口 + 系统托盘，不再需要打开浏览器
- **JS Bridge**：前后端同进程，无 HTTP，无端口
- **非线性行进**：每条 entry 独立打 `phase_index`，允许任意跳跃
- **多色环形图**：每阶段一段弧，弧长 = 该阶段记录占比
- **阶段演化**：AI 检测到阶段不合适会提议新结构（`evolve` action），用户确认后落地，旧 entry 按映射重打
- **周期循环**：投稿 / 考试结束后再开新一轮，自动开周期；Dashboard 可切「当前周期 / 全部」
- **深色 UI**

## 目录

```
main.py                 入口：双窗口 + 托盘 + 全局热键
tray.py                 系统托盘
api.py                  JS Bridge（submit/get_dimensions/confirm_evolution/...）
ai_processor.py         DeepSeek + update/create/evolve/confirm/skip
data_store.py           progress.json 读写 + v1→v2 schema 迁移
weekly_report.py        周报脚本
autostart.py            开机自启注册 / 取消
config.py               API key、模型、端口
ui/
├── input.html          快速粘贴窗
├── dashboard.html      仪表盘
├── style.css           深色主题
└── dashboard.js
data/
├── progress.json       预置 6 维度
└── weekly/             周报存放
```
