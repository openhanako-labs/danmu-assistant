# AI 弹幕助手 v2.0


![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)


> 月曦夜的赛博弹幕机 — 让 AI 看懂你的屏幕，听懂你的话，然后替你发弹幕。

---

## 🎯 是什么

一款运行在桌面的实时弹幕生成工具。它**截取你的游戏/直播/工作画面**，调用视觉模型理解内容，同时**监听你的麦克风**，把画面+语音综合成 B 站风格的弹幕，通过全屏透明浮层飘出来。

**特点**：不打扰操作、鼠标穿透、顶部 30% 区域、支持文件弹幕源、退出生成统计文件。

---

## ✨ 功能

| 功能 | 状态 | 说明 |
|------|------|------|
| AI 截屏弹幕 | ✅ | 每 8 秒截屏 → 视觉模型分析 → 生成 2-3 条弹幕 |
| 语音理解弹幕 | ✅ | 麦克风收音 → ASR 识别 → AI 理解 → 互动弹幕 |
| 文件弹幕源 | ✅ | 监控 `danmu_source.txt`，写入即发 |
| 全屏透明浮层 | ✅ | PyQt6 全屏窗口，鼠标穿透，不挡操作 |
| 防重叠 | ✅ | 10 轨道 + 时间冷却，弹幕不叠一起 |
| 去重 | ✅ | 60 秒窗口内不重复 + 语义相似过滤 |
| 逐条发送 | ✅ | 0.6 秒间隔，节奏自然 |
| 随机数量 | ✅ | 每次 1-4 条随机，更自然 |
| 去重 | ✅ | 60 秒窗口内不重复 + 语义相似过滤 |
| 逐条发送 | ✅ | 0.6 秒间隔，节奏自然 |
| 随机数量 | ✅ | 每次 1-4 条随机，更自然 |
| 退出统计 | ✅ | 自动生成 `danmu_stats_YYYYMMDD_HHMMSS.txt` |
| 三层 ASR | ✅ | API > whisper.cpp > faster-whisper，可配置 |
| **9 种弹幕风格** | ✅ | pi/normal/serious/tucao/kuakua/wenyi/shadiao/lengyoumo/fanquan |

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────┐
│                    main.py (入口)                  │
├────────────┬────────────┬────────────┬───────────┤
│ 截屏线程   │ 语音线程    │ 文件监控   │ 统计面板   │
│ DanmuAI    │ VoiceDanmu │ DanmuFile  │ DanmuStats│
├────────────┴────────────┴────────────┴───────────┤
│              DanmuOverlay (PyQt6 浮层)            │
│          DanmuEngine (10 轨道 / 防重叠)           │
└──────────────────────────────────────────────────┘
```

### 三层 ASR 识别

```
用户说话
  │
  ▼
[ASR API] ← 远程 API（stepfun / openai / siliconflow）
  │ 成功 → 返回文字
  │ 失败
  ▼
[whisper.cpp] ← 本地 C++ 引擎（ggerganov/whisper.cpp）
  │ 成功 → 返回文字
  │ 失败
  ▼
[faster-whisper] ← Python fallback（tiny/base/small）
  │
  ▼
识别结果 → AI 理解 → 生成弹幕
```

---

## 📦 目录结构

```
danmu-assistant/
├── main.py                 # 入口，整合所有模块
├── config.yaml             # 全局配置
├── danmu_ai.py             # 截屏 + 视觉模型弹幕
├── voice_danmu.py          # 语音理解弹幕（三层 ASR）
├── danmu_file_source.py    # 文件弹幕源监控
├── danmu_overlay_full.py   # 全屏透明浮层 + 轨道引擎
├── danmu_overlay_pyqt.py   # PyQt6 窗口封装
├── danmu_stats_panel.py    # 统计面板
├── danmu_source.txt        # 文件弹幕源（写一行发一条）
└── README.md
```

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- Windows 10/11
- 麦克风（可选，用于语音弹幕）
- 多显示器（可选，自动适配）

### 2. 安装依赖

```bash
pip install pyqt6 mss pillow sounddevice faster-whisper pyyaml
```

### 3. 配置

编辑 `config.yaml`：

```yaml
# 视觉模型 API
vision_api:
  provider: siliconflow
  base_url: https://api.siliconflow.cn/v1
  model: Qwen/Qwen3.5-397B-A17B
  api_key: sk-xxx

# 语音配置
voice:
  enabled: true
  sample_rate: 48000    # WASAPI 麦克风默认采样率
  whisper_model: tiny   # faster-whisper 模型（tiny/base/small）
  device: cpu
  compute_type: int8

  # 可选：远程 ASR API（优先级高于本地 whisper）
  asr_api:
    provider: ""        # stepfun / openai / siliconflow
    base_url: ""
    api_key: ""
    model: ""

  # 可选：whisper.cpp（优先级高于 faster-whisper）
  whisper_cpp:
    enabled: false
    exe_path: ""
    model_path: ""
    language: "zh"
    threads: 4
```

### 4. 运行

```bash
python main.py
```

### 5. 使用

- **AI 弹幕**：自动每 8 秒截屏分析
- **语音弹幕**：对着麦克风说话，识别后 AI 生成互动弹幕
- **文件弹幕**：往 `danmu_source.txt` 写文字，回车即发
- **退出**：Ctrl+C，自动生成统计文件

## 🎮 弹幕风格

支持 9 种弹幕风格，在 `config.yaml` 的 `danmu_ai_style` 切换：

| 风格 | 代号 | 说明 |
|------|------|------|
| 玩梗/皮 | `pi` | 默认，吐槽玩梗网络用语 |
| 自然随意 | `normal` | 像普通观众发弹幕 |
| 正经描述 | `serious` | 客观描述，适合教学 |
| 犀利吐槽 | `tucao` | 阴阳怪气毒舌开炮 |
| 真诚赞美 | `kuakua` | 彩虹屁拉满 |
| 文艺诗意 | `wenyi` | 氛围感，适合风景剧情 |
| 沙雕无厘头 | `shadiao` | 抽象派，越离谱越好 |
| 冷幽默 | `lengyoumo` | 简短反差一本正经 |
| 饭圈化 | `fanquan` | 尖叫姨母笑老婆狂喊 |

运行时可通过 `DanmuAI.set_style("tucao")` 动态切换。

---

## 🎮 弹幕效果

- **全屏透明**：4608×1280（适配 2K 双屏）或自动适配主屏
- **鼠标穿透**：点击穿透到游戏/应用，不挡操作
- **顶部 30%**：只在上方显示，不挡游戏 UI
- **10 轨道**：防重叠，同一轨道 2 秒冷却
- **去重**：15 秒内不重复，语义相似过滤
- **逐条发送**：0.6 秒间隔，自然节奏

---

## 🔧 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 浮层 | PyQt6 + Win32 API | 全屏透明 + WS_EX_TRANSPARENT 鼠标穿透 |
| 截屏 | mss | 高效跨平台截屏 |
| AI 视觉 | siliconflow Qwen3.5-VL | 画面理解 + 弹幕生成 |
| 语音 | sounddevice | 实时麦克风输入 |
| ASR | 三层架构 | API > whisper.cpp > faster-whisper |
| 弹幕引擎 | 自定义轨道系统 | 10 轨道 + 时间冷却 + 碰撞检测 |
| 统计 | Queue + QTimer | 线程安全，主线程消费 |

---

## 📝 当前状态

- **Phase 1** ✅ 完成：截屏弹幕 + 语音弹幕 + 文件弹幕源 + 浮层 + 统计
- **Phase 2** ✅ 完成：关键帧检测 + 弹幕皮肤 + 说话人分离 + 窗口聚焦
- **Phase 3** ✅ 完成：9 种弹幕风格 + 浮层引擎合并 + 统计面板修复
- **Phase 4** ⏳ 待开始：Hanako WebSocket 联动 + 桌宠联动 + 运行时风格切换 UI

---

## 🐛 已知问题

- [ ] whisper.cpp 尚未集成（骨架已写好，需下载 whisper-cli.exe + 模型）
- [ ] stepfun API 返回空 content（reasoning 模型兼容性问题）
- [ ] 浮层坐标在多显示器切换时可能偏移
- [ ] 语音弹幕延迟约 1.5-2 秒（CPU 限制）

---

## 许可

本项目采用**双重许可**：

- **开源许可**：[GNU AGPL v3](https://www.gnu.org/licenses/agpl-3.0.html) — 开源免费，但修改必须开源
- **商业许可**：闭源使用需购买商业授权，详见 [COMMERCIAL-LICENSE.md](./COMMERCIAL-LICENSE.md)

---

*奥菲莉娅整理 · 2026-06-28*
