---
name: ark-deskpet-skill
description: Build transparent desktop pets (桌宠) for Arknights operators from PRTS model exports and pair them with WorkBuddy. Use when the user wants to make a deskpet from an Arknights operator, download operator model/WebM animations, add an operator to the deskpet library, switch the active pet, or pair the pet with WorkBuddy's lifecycle. The skill handles PRTS scraping, WebM -> transparent PNG extraction, scaffold-and-run of the cross-platform pet app (Windows, macOS, Linux), and the host-process watcher that shows the pet while WorkBuddy is running.
---

# Ark Deskpet Skill (WorkBuddy edition)

Generate a transparent desktop pet for an Arknights operator from PRTS
operator models, store it in a reusable library, and pair it with
WorkBuddy's lifecycle so the pet only stays around while you're actually
working in WorkBuddy.

> Originally forked from `AstrariaX/Ark-codex-skill` (Codex edition). This
> fork decouples the host watcher, the session monitor, and the visual
> surfaces ("Codex" titles, registry keys, default process names) from
> the Codex desktop app and re-points them at WorkBuddy. The runtime is now
> cross-platform — Windows, macOS, and Linux desktops are all supported.

## When to use this skill

- User asks for a "明日方舟 桌宠" / "Arknights deskpet" / "干员桌宠"
- User mentions PRTS, 干员模型, WebM, or wants the operator animations extracted
- User wants to swap the active pet ("换成阿米娅", "切换干员")
- User wants to configure pet behavior (size, mini mode, autostart with WorkBuddy)

## Workflow

1. **Confirm the operator and (optional) skin.** If no skin is given, default
   to `默认`.
2. **Scaffold a project directory** (or reuse an existing one). The project
   ships with no bundled character frames; the workflow is meant to scrape
   PRTS for whatever operator you want and add it to the library in the
   same run.
3. **Export `base` (基建) WebM animations** from PRTS: `Default`, `Interact`,
   `Move`, `Relax`, `Sit`, `Sleep`. The `Default` WebM is often a broken
   110-byte file; keep it for reference but skip it when extracting frames.
4. **Extract transparent PNG frames** at 1000x1000, 20fps. Compute bounding
   boxes and write `pets/<operator>/manifest.json`.
5. **Pair with WorkBuddy.** The launcher watches for the WorkBuddy process
   (default names: `WorkBuddy`, `WorkBuddy Helper`, `WorkBuddyHelper`,
   `WorkBuddy.exe`, `WorkBuddyHelper.exe`, `WorkBuddyClient.exe`).
   Override the list via `settings.json -> host_processes` if your build
   uses a different executable name.

## Quick Start on a Fresh Machine

> **Platform note:** the desktop pet runtime uses `PySide6`. Process
> listing, fullscreen detection, and login autostart are all abstracted
> in `_platform.py` and work cross-platform (Windows / macOS / Linux).
> PRTS export and frame extraction scripts use Playwright Chromium
> and also run cross-platform.

```bash
# 1. Scaffold a new deskpet project and create a project-local venv.
#    Pass --skip-browser on systems where Playwright Chromium cannot be
#    downloaded; the scripts will then fall back to system Chrome.
python scripts/scaffold_deskpet.py --target <project-dir> --pet "<operator>"
python scripts/setup_env.py <project-dir>

# 2. Export WebM from PRTS (default skin unless --skin is given).
python scripts/prts_export.py "<operator>" [--skin "<skin>"] \
    --out <project-dir>/work/webm

# 3. Convert WebM to transparent frames and register the pet in the library.
python scripts/process_webm.py \
    --src <project-dir>/work/webm \
    --name "<operator>" \
    --out <project-dir>/pets/<operator>

# 4. Launch:
#    - Windows: double-click 启动桌宠.bat
#    - macOS / Linux:  ./启动桌宠.sh
```

## Pairing with WorkBuddy

The launcher (`pet_launcher.pyw`) is the lifecycle bridge. It is a small
background process that:

- Detects WorkBuddy (or any process in `host_processes`) at startup.
- When WorkBuddy is running: spawns the pet window and a tray icon.
- When WorkBuddy exits: closes the pet and tray.
- Quits cleanly when the user clicks **Exit** in the tray.

Default host process names watched by the launcher:

```text
workbuddy.exe / workbuddy
workbuddyhelper.exe / workbuddy helper / workbuddy helper (renderer)
workbuddyclient.exe / workbuddyclient
```

> **Tip:** match exactly what your platform shows in the process list
> (e.g. Task Manager on Windows, Activity Monitor on macOS, ``ps -A`` on
> Linux). Everything is matched case-insensitively against the executable
> basename. Add or override names by editing `settings.json` next to
> `main.py`:

```json
{
  "host_processes": ["MyWorkBuddyBuild", "WorkBuddy"]
}
```

## Status subtitles (headline bar)

The pet shows a small subtitle bar above itself. It reads from
`~/.workbuddy/memory/` (and any `session_paths` you add), picks the most
recently edited file, and shows whichever fields it can find:

| Field        | Where it looks                                                     |
| ------------ | ------------------------------------------------------------------ |
| `task`       | `# 当前任务` / `# 任务` headings, or last `user_message` in JSONL |
| `model`      | `# 模型` heading, or `payload.model` in JSONL                     |
| `progress`   | `# 进度` / `# 进展`, or last `agent_message`                      |
| `elapsed`    | elapsed since `started_at`                                         |
| `tokens`     | `payload.info.total_token_usage.total_tokens` (or `# Token` num) |
| `last_finished` | `HH:MM` of last `completed_at`                                  |

If the file format is unknown, the subtitle falls back to `"WorkBuddy 待机"` /
`"WorkBuddy 运行中"` based on the file's mtime only.

To extend scanning to more directories (project-level memory, custom logs,
legacy Codex sessions), add paths to `settings.json`:

```json
{
  "session_paths": ["~/.workbuddy/memory", "~/projects/my-app/.workbuddy"]
}
```

## Scripts

| Script                       | What it does                                                          |
| ---------------------------- | --------------------------------------------------------------------- |
| `scaffold_deskpet.py`        | Copy the app template into a project and write initial `settings.json` |
| `setup_env.py`               | Create `.venv`, install `PySide6` + `playwright`, install Chromium    |
| `prts_export.py`             | Scrape PRTS model viewer, download the six base WebM animations       |
| `process_webm.py`            | Decode WebM in Chromium, extract transparent PNGs, compute bounding box |
| `prts_dialogue.py`           | Scrape PRTS `语音记录` section for an operator's Chinese voice lines into raw JSON (see *Refreshing dialogue lines* below) |
| `create_shortcuts.py`        | Create shortcuts for the project on the current platform: `.lnk` on
Windows, `.command` in `~/Applications` on macOS, `.desktop` in
`~/.local/share/applications` on Linux                              |

## Refreshing dialogue lines

Each pet's offline dialogue lives in `pets/<character>/dialogue.json`. Logos
ships with a curated script whose every line is pulled from PRTS Wiki's
`语音记录` section (Chinese-普通话 voice overs). To refresh or rebuild
those lines for *any* operator:

```bash
python scripts/prts_dialogue.py "<operator中文或英文名>" \
    --out work/dialogue_raw.json --pretty
```

The output JSON is the raw catalog (one entry per cue, fields:
`index / title / place / cond / file / text`). Mapping a cue into a
`dialogue.json` bucket — and writing the long-form cues to
`pets/<character>/long_lines.json` for the chat assistant to reference —
is a curation step, intentionally kept manual (the dialogue engine
already knows how to consume either format). If PRTS changes how the
`#voice-data-root` block is rendered, update the parser in
`scripts/prts_dialogue.py` accordingly.

## Notes

- The PRTS `Default` WebM export is usually a broken 110-byte file; keep it
  in `webm/` for reference but do not map it to any state.
- If PRTS changes its viewer DOM, update `references/prts-ui.md` and the
  selectors inside `scripts/prts_export.py`.
- The generated app remembers position, size, and speed per pet, supports
  a mini mode, and can auto-hide in fullscreen.
- The tray offers `显示桌宠`, `隐藏桌宠` (closes the pet), `开机自启动`, and
  `退出` (closes pet, tray, and watcher). The tray disappears when
  WorkBuddy exits.
- The app template ships without any bundled character frames. Run the
  Quick Start steps (`scaffold_deskpet.py` → `prts_export.py` →
  `process_webm.py`) before launching, or add a freshly exported pet from
  the right-click `桌宠库` menu.
- The pet only reads host data; it never writes anything under
  `~/.workbuddy/` or your project memory.

## Talk with your pet (DeepSeek)

The pet can chat with you through a streaming dialog wired to DeepSeek's
OpenAI-compatible API. The chat window opens from the right-click menu
(`聊天...`) and is fully opt-in.

**Setup**

1. Sign up at https://platform.deepseek.com and create an API key.
2. Right-click the pet → `设置...` → 聊天 (DeepSeek) → 勾选 `启用聊天`.
3. Paste your `sk-...` key into the API Key field.
4. (Optional) Adjust Base URL / 模型 / System Prompt if you proxy
   DeepSeek or want a different persona. Defaults are
   `https://api.deepseek.com/v1` and `deepseek-chat`.

**Behavior**

- Tokens stream in live; the bot bubble fills incrementally.
- Esc / closing the window aborts an in-flight response.
- History lives in memory only — nothing is persisted between sessions.

**Privacy**

The API key is stored in `settings.json` next to `main.py`. The pet only
talks to the configured `base_url`; no other endpoint is contacted. Use a
dedicated key if you want it scoped.

All chatter settings (`chatter_enabled`, `deepseek_api_key`,
`deepseek_base_url`, `deepseek_model`, `deepseek_system_prompt`) live in
`settings.json` and can also be edited from the Settings dialog. The
`聊天...` menu item is disabled until both `chatter_enabled` and
`deepseek_api_key` are set.

## Troubleshooting

**PRTS export fails or the load button is gone.** The PRTS page may have
been redesigned. Check `references/prts-ui.md` for the current DOM and
update the selectors in `scripts/prts_export.py`.

**Pet launches but no character is visible.** Run `调试运行.sh` (macOS / Linux)
or `调试运行.bat` (Windows) next to `main.py`, copy the console output, or read
`pet_error.log`.

**Need to download the assets manually.** In the PRTS model viewer:

1. Click `点此载入模型`.
2. Pick `默认` (or your skin) under 时装组.
3. Pick `基建` under 模型组.
4. Iterate the `动画` dropdown through `Default / Interact / Move / Relax /
   Sit / Sleep`, downloading the WebM each time.
5. Drop the files into `<project-dir>/work/webm/` and re-run
   `process_webm.py`.

**Pet never appears despite WorkBuddy running.** The launcher couldn't
match your WorkBuddy executable name. Add it to
`settings.json -> host_processes` (use the exact basename you see in
Activity Monitor / Task Manager / `ps`) and the next polling cycle will
pick it up.

**Login autostart does not register on macOS.** macOS may prompt the
first time the LaunchAgent is installed (`launchctl load`). Allow it
when prompted. The autostart entry is at
`~/Library/LaunchAgents/com.user.ark-deskpet.plist`.

**Linux fullscreen auto-hide never triggers.** Cross-DE fullscreen
detection is unimplemented — disable the "全屏应用时自动隐藏" toggle if
it gets in the way.

## Attribution & licensing

- 《明日方舟》素材版权归 Hypergryph 所有，PRTS 资料遵循其站内许可。
- 本项目仅用于个人学习与自用，请勿用于商业发布。
- Forked from `AstrariaX/Ark-codex-skill` (Codex edition) by the
  community. See the original repository for prior history.
