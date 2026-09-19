# Ark Deskpet Skill (WorkBuddy 版)

给干员做一个透明桌面桌宠，并让 WorkBuddy 来当
宿主：WorkBuddy 在就显示，关掉就一起退。原版（Codex 绑定）见
[`AstrariaX/Ark-codex-skill`](https://github.com/AstrariaX/Ark-codex-skill)，
这个仓库是它的 WorkBuddy 分叉。

> 仓库结构：外层是 README 和安装包描述，里面的 `ark-deskpet-skill/` 才是
> 可安装到 `~/.workbuddy/skills/` 的 skill 本体。

## 它能做什么

- 检索 PRTS Wiki 干员页面，自动加载"干员模型"查看器
- 默认原皮（默认时装），也可指定任意时装组
- 模型组固定"基建"，导出 `Default / Interact / Move / Relax / Sit / Sleep`
  六段动画
- 自动跳过 PRTS 坏文件（`Default` 通常是 110 字节空文件）
- 把 WebM 抽成 1000x1000、20fps 的透明 PNG，自动算包围盒并写
  `manifest.json`
- 桌宠库：可以一次存多个干员，右键"桌宠库"随时切换
- 系统托盘：检测到 WorkBuddy 进程时拉起托盘，提供"显示桌宠 / 隐藏桌宠 /
  开机自启动 / 退出"，WorkBuddy 退出时托盘一起退出
- 一键生成桌面和开始菜单的"打开桌宠 / 启动托盘"快捷方式
- 项目模板初始自带一个空 `pets/` 占位，生成后先用本 skill 抓一个干员入
  库（建议参考 SKILL.md 的"快速开始"四步），再启动桌宠
- 生成的项目自带完整桌宠程序：状态字幕、拖动、锁定、迷你模式、全屏自动隐藏、
  按角色记忆位置 / 大小 / 倍速、随 WorkBuddy 启动

## 监听器说明

`pet_launcher.pyw` 是一个轻量常驻监听器，负责整个生命周期：

- 检测到 WorkBuddy 启动时，拉起桌宠和托盘进程
- 检测到 WorkBuddy 退出时，关闭桌宠和托盘进程
- 托盘图标 `pet_tray.pyw` 只在 WorkBuddy 运行期间存在

默认监听以下进程名（区分大小写不敏感）：

```text
WorkBuddy.exe
WorkBuddy
WorkBuddyHelper.exe
WorkBuddy Helper.exe
WorkBuddyClient.exe
```

如果你的 WorkBuddy 安装包 exe 名不一样，在项目目录里的 `settings.json`
里加一行 `host_processes` 即可，例如：

```json
{
  "host_processes": ["WorkBuddyPro.exe", "WorkBuddy.exe"]
}
```

如果监听器被手动退出（例如托盘里的"退出"），WorkBuddy 再次启动时不会
自动拉起桌宠。恢复方式：

1. **Windows**：下次登录时注册表 `ArkDeskpetWatcher` 会自动启动监听器
2. **macOS**：下次登录时 LaunchAgent `com.user.ark-deskpet` 会自动启动
3. **Linux**：桌面会话启动时 `~/.config/autostart/ark-deskpet.desktop` 触发
4. 或在项目目录下手动跑 `启动桌宠.sh` / `启动桌宠.bat` 恢复

托盘菜单说明：

- `显示桌宠`：显示或重新拉起桌宠
- `隐藏桌宠`：关闭桌宠（功能等同原来的"完全退出桌宠"），托盘保留，
  可再次用"显示桌宠"打开
- `开机自启动`：勾选后登录系统时自动启动监听器
- `退出`：关闭桌宠、托盘和监听器本身

## 快捷方式

`scripts/create_shortcuts.py` 按当前平台写入启动入口：

| 平台 | 入口 | 位置 |
| --- | --- | --- |
| Windows | `打开桌宠.lnk` / `启动托盘.lnk` | 桌面 + 开始菜单 |
| macOS | `打开桌宠 (Ark Deskpet).command` / `启动托盘 (Ark Deskpet).command` | `~/Applications`（附带尝试 pin 到 Dock） |
| Linux | `ark-deskpet-打开桌宠.desktop` / `ark-deskpet-启动托盘.desktop` | `~/.local/share/applications` |

## 目录结构

```text
ark-deskpet-skill/
├── README.md
├── .gitignore
└── ark-deskpet-skill/             # 可安装的 skill 本体
    ├── SKILL.md                 # WorkBuddy skill 主说明
    ├── scripts/
    │   ├── scaffold_deskpet.py  # 生成桌宠项目
    │   ├── setup_env.py         # 创建 .venv 并安装依赖
    │   ├── prts_export.py       # 从 PRTS 导出 WebM
    │   ├── process_webm.py      # WebM 转透明 PNG 帧
    │   └── create_shortcuts.py  # 创建桌面/启动器快捷方式（跨平台）
    ├── references/
    │   └── prts-ui.md           # PRTS 查看器 DOM 参考
    └── assets/
        └── deskpet-app/         # 桌宠应用模板
            ├── _platform.py     # 跨平台抽象（进程/自启动/全屏）
            ├── deepseek_client.py  # DeepSeek 流式 API 客户端
            ├── chat_dialog.py  # 聊天 QDialog
            ├── main.py
            ├── pet_launcher.pyw # 监听器
            ├── pet_tray.pyw     # 托盘
            ├── workbuddy_monitor.py
            ├── 启动桌宠.sh     # macOS / Linux
            ├── 启动桌宠.bat     # Windows
            ├── 调试运行.sh
            ├── 调试运行.bat
            └── pets/  # 由 skill 抓出来的角色
```

## 环境要求

- Windows 10/11、macOS 12+、主流 Linux 桌面（桌宠运行时已跨平台）
- Python 3.10 或更高版本（3.13+ 推荐）
- 可访问 `https://prts.wiki`
- 有网络权限安装依赖（PySide6、Playwright）
- macOS 上 PySide6 通过 `pyobjc` 间接拿到 Quartz，所以无需额外装系统包

所有依赖都安装到项目自己的 `.venv`，不会影响全局 Python 环境。

## 使用指南

### 第一步：部署这个 skill

对 WorkBuddy 说：

```text
安装 ark-deskpet-skill 这个 skill（来自本地路径 ark-deskpet-skill/）
```

也可以手动安装：把仓库里的 `ark-deskpet-skill/` 目录复制到
`~/.workbuddy/skills/ark-deskpet-skill/`。

如果 WorkBuddy 提供了 skill 安装器，指定 `--repo AstrariaX/Ark-codex-skill`
或本地路径即可。

### 第二步：调用 skill

默认原皮：

```text
用 ark-deskpet-skill 制作干员 浊心斯卡蒂 的桌宠
```

指定皮肤：

```text
用 ark-deskpet-skill 制作干员 浊心斯卡蒂 的桌宠，皮肤用 升华
```

不写皮肤就是默认原皮。制作完成后右键小人 -> 桌宠库，可以随时切换已
入库的角色。

注意：项目初始不带任何预设角色，需要先用 skill 跑一次
"`scaffold_deskpet.py` → `prts_export.py "<干员>"` → `process_webm.py`"
之后才能 `启动桌宠.sh`（macOS/Linux）或 `启动桌宠.bat`（Windows）；想
加入更多角色时同样走一遍流程。

## 桌宠功能

- 单击播放互动动画
- 双击切换迷你模式（隐藏 / 显示字幕条）
- 拖动播放走路动画，松手恢复之前状态
- 右键菜单：坐下 / 放松 / 睡觉 / 桌宠库 / 锁定 / 设置 / 放大 / 缩小 /
  隐藏到托盘 / 完全退出
- 头顶字幕：WorkBuddy 运行状态、最近任务、模型、运行时长、Token 用量、
  最近完成时间
- 每个角色独立记住位置、大小、动作倍速
- 迷你模式、全屏应用自动隐藏
- 可设置随 WorkBuddy 启动和关闭
- 只读 `~/.workbuddy/memory/` 等可选 session 路径

## 常见问题

### PRTS 导出失败或按钮找不到

PRTS 页面改版会影响脚本。先看 `ark-deskpet-skill/references/prts-ui.md`
里的 DOM 说明，再同步更新 `ark-deskpet-skill/scripts/prts_export.py` 的
选择器。

### 打开后没有看到小人

- **Windows**：运行 `my-deskpet/调试运行.bat`
- **macOS / Linux**：跑 `./my-deskpet/调试运行.sh`

把控制台报错或 `pet_error.log` 内容发出来。

### WorkBuddy 在跑，托盘不出现

监听器进程的进程名匹配没命中。在 `my-deskpet/settings.json` 里加
`host_processes`（用活动监视器 / 任务管理器看到的进程名），重启
`pet_launcher.pyw`。

### macOS 上启动后看不到小人

- 第一次运行 PySide6 时，macOS 可能弹"是否允许控制"，同意即可
- 若托盘图标丢失，检查系统设置 `控制中心 -> 菜单栏额外项 -> 明日方舟桌宠` 是否被禁用

### 聊天窗口打不开或一直报错

- 右键菜单里的"聊天..."是灰色的 → 还没在 设置... 里勾上 启用聊天
- 点了之后弹"尚未配置 API Key" → 设置... → 聊天 (DeepSeek) 里填 sk-...
- 报"网络错误" → 检查网络；自定义 base_url 的话注意 Base URL 不能带
  末尾斜杠
- 报 401 / 403 → API Key 失效，去 https://platform.deepseek.com 重置

### 需要手动从网站下载素材

可以直接在 PRTS 干员页的"干员模型"里手动操作：

1. 点击"点此载入模型"
2. 时装组选默认（或指定皮肤）
3. 模型组选"基建"
4. 动画依次选 `Default / Interact / Move / Relax / Sit / Sleep`
5. 点击下载图标按钮导出 WebM
6. 把文件放进 `my-deskpet/work/webm/`，再让 skill 继续抽帧入库

## 注意事项

- 《明日方舟》素材版权归 Hypergryph 所有，PRTS 资料遵循其站内许可。
  本项目仅用于个人学习与自用，请勿用于商业发布。
- 桌宠运行时已支持 Windows / macOS / Linux；Linux 上"全屏应用时自动隐藏"
  当前不做跨 DE 探测（会等到窗口管理器支持扩展 API 后补上）。

## 与原 Codex 版的差异

| 维度            | 原 Codex 版                          | 本仓库（WorkBuddy 版）                        |
| --------------- | ------------------------------------- | ---------------------------------------------- |
| 监听目标        | `chatgpt.exe`、`codex.exe`            | `WorkBuddy*`、`WorkBuddyHelper*` 等，可配置 |
| 会话读取        | `~/.codex/sessions/*.jsonl`           | `~/.workbuddy/memory/` 等，多格式容错          |
| 自启动注册      | Win 注册表                            | Win 注册表 / macOS LaunchAgent / Linux XDG autostart |
| 托盘图标字符    | `C`                                   | `A`                                              |
| 字幕文案        | "Codex 运行中" / "Codex 待机"          | "WorkBuddy 运行中" / "WorkBuddy 待机"           |
| 安装目录约定    | `~/.codex/skills/`                    | `~/.workbuddy/skills/`                          |
| 运行平台        | Windows only                          | Windows / macOS / Linux                       |

## 贡献

欢迎提交 PR 修复 PRTS 页面变动、增加新动画映射、优化抽帧速度或补充
平台适配。
