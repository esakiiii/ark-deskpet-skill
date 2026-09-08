# 明日方舟 桌宠 (WorkBuddy 版)

一个使用 Python 虚拟环境 + PySide6 的透明桌面宠物库，可以显示 WorkBuddy
的"当前是否活跃"和最近的会话状态。项目初始不带任何角色框架——需要先
用 `ark-deskpet-skill` 把干员（默认建议 望）从 PRTS 抓下来入库。

## 运行

依赖都装在项目目录内的 `.venv`，不会影响全局的 Python、Node、npm 环境。

按系统双击对应启动器：

- **Windows**：双击 `启动桌宠.bat`（调 `.venv\Scripts\pythonw.exe`，不弹黑色控制台）
- **macOS / Linux**：跑 `./启动桌宠.sh`（先 `chmod +x`）

如果启动后没有看到小人，分别跑 `调试运行.bat` / `./调试运行.sh` 看报错，或把
`pet_error.log` 贴过来。

## 操作

- 单击：播放互动动画，播完回到待机
- 双击：切换迷你模式（隐藏 / 显示字幕条）
- 拖动：播放走路动画，松开后回到之前的状态
- 右键选择坐下、放松、睡觉后会循环播放对应动作，不会只播一次就回待机
- 右键 -> 桌宠库：随时切换已入库的角色
- 锁定：右键菜单切换"解锁拖动 / 锁定拖动"，锁定后鼠标不会移动桌宠
- 右键：坐下 / 放松 / 睡觉 / 桌宠库 / 解锁或锁定拖动 / 设置 / 放大 / 缩小
  / 隐藏到托盘 / 完全退出
- 右键菜单可单独开关"迷你模式"和"全屏应用时自动隐藏"
- 右键"隐藏到托盘"只隐藏窗口，托盘里随时可以再显示
- 右键"完全退出"会真正关闭桌宠，即使 WorkBuddy 还在运行也不会被重新
  拉起，直到应用下次启动
- 页面上没有加减号，大小调整都在右键菜单里

## 系统托盘

轻量监听器负责生命周期，不占用托盘；检测到 WorkBuddy 运行时才拉起托盘
进程，菜单提供：

- 显示桌宠
- 隐藏桌宠（关闭桌宠，功能等同原来的"完全退出桌宠"）
- 开机自启动
- 退出

WorkBuddy 退出时，监听器会关闭桌宠和托盘进程，托盘图标消失。
"退出"会同时关闭桌宠、托盘和监听器本身。

## 监听器说明

`pet_launcher.pyw` 是轻量常驻监听器，负责跟随 WorkBuddy 启动和关闭桌宠
与托盘。

- WorkBuddy 启动时：拉起桌宠和托盘
- WorkBuddy 退出时：关闭桌宠和托盘
- 监听器被手动退出后，WorkBuddy 再次启动不会自动拉起桌宠；下次登录会
  自动恢复（macOS LaunchAgent / Win Run / Linux XDG autostart），或
  手动跑 `启动桌宠.{sh,bat}` 恢复

默认监听以下进程名（在 `settings.json -> host_processes` 里可覆盖）：

```text
workbuddy / workbuddy.exe
workbuddyhelper / workbuddyhelper.exe
workbuddy helper / workbuddy helper (renderer)
workbuddyclient / workbuddyclient.exe
```

## 快捷方式

在桌面和开始菜单创建两个快捷方式：

```bash
python <skill目录>/scripts/create_shortcuts.py --project <桌宠项目目录>
```

- `打开桌宠.lnk`：直接启动桌宠
- `启动托盘.lnk`：启动监听器（托盘），监听器退出后可用它恢复

## 设置

右键 -> 设置...

- 动作倍速：0.5x / 0.75x / 1.0x / 1.25x / 1.5x
- 字幕长度：简短 / 标准 / 详细，控制头顶字幕显示多少 WorkBuddy 信息
- 字幕大小：14-26px 滑块调节
- 字条长度：40%-100% 滑块调节，控制头顶字幕条的宽度
- 迷你模式：隐藏字幕条，只显示小人
- 全屏应用时自动隐藏：检测到全屏窗口时隐藏桌宠
- 随 WorkBuddy 启动：开启后会在当前用户注册表写入监听器，登录后
  检测到 WorkBuddy 启动就拉起桌宠，应用退出时也会一起关闭桌宠
- 每个角色会记住自己的位置、大小和动作倍速，切换角色后自动恢复

## 状态字幕

- 简短：WorkBuddy 运行中 / 待机 + 最近任务
- 标准：再加上当前模型、运行时长、Token 用量
- 详细：再加上最近完成时间、最近运行进度

桌宠只读 `~/.workbuddy/memory/`（以及 `settings.json -> session_paths`
里配置的目录）下的会话记录，不会修改 WorkBuddy 的任何数据。

## 桌宠库

角色目录放在 `pets/` 下，每个目录包含 `manifest.json`、`frames/` 动画帧
和 `webm/` 原始素材。

- 默认建议 `望`：原皮（默认）时装、基建模型，需要先用 skill 生成
- `浊心斯卡蒂`：默认时装、基建模型（示例，需要先用 skill 生成）

## 聊天（DeepSeek）

右键菜单 → `聊天...` 打开聊天窗。token 一边生成一边显示，按 Esc 中断。
需要先用 `设置...` 勾上启用聊天并填好 DeepSeek API Key：

- 申请：<https://platform.deepseek.com>
- 默认 Base URL：`https://api.deepseek.com/v1`
- 默认模型：`deepseek-chat`
- 可选 System Prompt：例如 `你是 Logos。保持简短，1-2 句内回答。`

历史只在内存里，关闭聊天窗就清空。API Key 存 `settings.json`，桌宠
只会向你配的 base_url 发请求。

`settings.json` 里的字段：

```json
{
  "chatter_enabled": false,
  "deepseek_api_key": "",
  "deepseek_base_url": "https://api.deepseek.com/v1",
  "deepseek_model": "deepseek-chat",
  "deepseek_system_prompt": ""
}
```

## 本地对话（dialogue.json，零 API 消耗）

桌宠自带一套离线台词库。每个角色可以放一个 `pets/<角色>/dialogue.json`，
不需要 API key、不消耗额度、立即返回。Logos 自带一份示例。

Logos 的台词**全部来自游戏本体**：用 `scripts/prts_dialogue.py` 从
PRTS Wiki 的「语音记录」section 抓出来，由人手工映射到 dialogue 分类
（greetings / idle / task_started / task_done / status_reactions /
reactions / fallback / long_idle）和权重。游戏里较长的整段（如「信赖提
升后交谈」「新年祝福」「生日快乐」）归档到伴侣文件
`pets/<角色>/long_lines.json`，对话聊天窗读这个，被 deepseek_client 的
system prompt 引用，但不直接喂给头顶气泡。

**会触发的场合**

- 右键菜单 → `聊天...`，用户输入**先**过 dialogue 匹配；命中即用、
  匹配不到再走 DeepSeek（如果命中的是 fallback 里的游戏短句，依然是
  游戏原文、不是 AI 自编）
- 桌宠待机时，每 60 秒随机抽一行 `idle` 台词，显示在头顶气泡里 5 秒
- `workbuddy_monitor` 检测到 WorkBuddy 任务**变化**或**完成**时，抽
  `task_done` / `task_started` 台词

**dialogue.json 格式**

```json
{
  "_meta": { "character": "Logos", "language": "zh-CN" },
  "greetings":  [ { "text": "……来了。", "weight": 2 }, ... ],
  "idle":       [ { "text": "……", "weight": 3 }, ... ],
  "task_done":  [ { "text": "完成了。", "weight": 2 }, ... ],
  "task_started": [ "开始吧。", "我在看。" ],
  "long_idle":  [ "……还在吗？" ],
  "reactions": [
    { "triggers": ["你好", "在吗"], "text": "在的。说吧。" },
    { "triggers": ["谢谢"],         "text": "……不用谢。" }
  ],
  "fallback":   [ "……嗯。", "继续说。" ]
}
```

`reactions` 里的 `triggers` 列表：英文按 word-boundary 匹配（`hi` 不会
撞 `history`），短 ASCII 触发词还接受前缀匹配（`thank` 命中 `thanks`），
中文走子串匹配。命中分数按 trigger 长度算，更长优先。

`greetings / idle / task_done / task_started / long_idle / fallback`
用 `weight` 字段加权随机抽（省略 `weight` 视为 1；可以混用纯字符串和
对象）。引擎会避开最近 6 条说过的台词防止刷屏。

**设置**

`settings.json -> dialogue_enabled` 开关（默认 true）。关闭后待机气泡
和聊天窗的 dialogue 匹配都不跑，只剩 DeepSeek。

每个角色的动画映射：

- `Relax` -> `idle`（待机）
- `Interact` -> `interact`（互动）
- `Move` -> `move`（移动 / 走路）
- `Sit` -> `sit`（坐下）
- `Sleep` -> `sleep`（睡觉）

PRTS 导出的 `Default` 文件是 110 字节的坏文件，所以没有使用。

## 资源占用

- 20fps，动画帧缓存限制在 5 帧以内
- 实测运行内存约 50-65 MB，10 秒 CPU 累计约 0.3 秒
- 两个角色的帧图片共约 160 MB 占用磁盘，不影响运行内存
