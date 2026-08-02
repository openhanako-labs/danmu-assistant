# AI 弹幕助手 — 代码清理计划

> 整理者：奥菲莉娅 | 版本：v1.1 | 日期：2026-06-28
> 状态：待执行
> 更新：新增「多样弹幕风格」需求

---

## 一、项目需求回顾

### 1.1 核心愿景
让 AI 真正"看懂"用户在做什么——通过截屏 + 语音 + AI 理解，实时生成弹幕评论。

### 1.2 三条弹幕流水线
| 来源 | 触发方式 | 说明 |
|------|---------|------|
| AI 截屏弹幕 | 定时截屏 → Qwen3.5-VL 视觉分析 | 分析画面内容生成弹幕 |
| 语音理解弹幕 | 麦克风收音 → ASR 识别 → AI 理解 | 听到什么说什么 |
| 文件弹幕源 | 往 txt 写一行 → 自动发射 | 手动/外部触发 |

### 1.3 风格偏好
- 弹幕风格：玩梗/皮/吐槽为主（`pi` 风格默认）
- 弹幕展示：全屏透明浮层 + 鼠标穿透 + 多轨道
- 统计面板：实时密度/情绪/高频词

### 1.3 弹幕风格
- **默认风格**：玩梗/皮/吐槽（`pi` 风格）
- **多样化风格切换**：用户要求支持多种弹幕风格选择（不只是单一风格）
- 待定义风格选项：皮/玩梗、正经描述、吐槽、夸夸、文艺、沙雕、冷幽默……

### 1.4 已知决策
- ~~OCR~~ 用户认为截图已够用，暂不需要 OCR 功能
- ~~本地 TTS 读弹幕~~ 用户明确表示不想要
- 参考项目：PEPETII/danmuai（取其精华，不 fork）
- 当前运行状态：正常

---

## 二、代码现状审计

### 2.1 活跃模块（main.py 正在使用）

| 文件 | 职责 | 状态 |
|------|------|------|
| `main.py` | 入口，整合三源 | ✅ 活跃 |
| `danmu_ai.py` | 截屏 + 视觉 AI 弹幕 | ✅ 活跃 |
| `voice_danmu.py` | 麦克风收音 + ASR | ✅ 活跃 |
| `asr_engine.py` | ASR 三层引擎抽象 | ✅ 活跃 |
| `danmu_overlay_full.py` | 全屏透明浮层 + 碰撞检测 | ✅ 活跃 |
| `danmu_stats_panel.py` | 统计面板 | ✅ 活跃 |
| `danmu_file_source.py` | 文件弹幕源 | ✅ 活跃 |
| `config.yaml` | 全局配置 | ✅ 活跃 |
| `tray_icon.py` | 系统托盘 | ✅ 待集成 |
| `hanako_danmu_bridge.py` | 弹幕→桌宠桥接 | ✅ 已实现但未接入 main.py |
| `danmu_skin.py` | 弹幕皮肤管理 | ✅ 已实现但未接入 main.py |
| `danmu_history.py` | 弹幕历史 | ✅ 已实现但未接入 main.py |
| `emotion_recognizer.py` | 情绪识别 | ✅ 已实现但未接入 main.py |
| `style_advisor.py` | 个性化风格 | ✅ 已实现但未接入 main.py |
| `keyframe_detector.py` | 关键帧检测 | ✅ 已实现但未接入 main.py |
| `window_capture.py` | 窗口聚焦截屏 | ✅ 已实现但未接入 main.py |
| `speaker_diarization.py` | 说话人分离 | ✅ 已实现但未接入 main.py |
| `stream_engine.py` | asyncio 异步流水线 | ⚠️ 未接入，依赖已死模块 |

### 2.2 重复/冲突模块

#### 浮层引擎 × 2
- `danmu_overlay_full.py` — 简单 paintEvent，**正在使用**
- `danmu_widget.py` — PyQt6 预渲染 + 脏区优化，**未使用**

#### Hanako 联动 × 2
- `hanako_link.py` — WebSocket 客户端，**未使用**
- `hanako_danmu_bridge.py` — HTTP + 阈值判定，**已实现未接入**

#### 音频管线 × 2
- `audio_input.py` — FunASR 本地方案，**已死**
- `voice_danmu.py` + `asr_engine.py` — 三层降级，**正在使用**

### 2.3 死代码（未引用）

| 文件 | 原因 |
|------|------|
| `audio_input.py` | 旧 FunASR 方案，被 voice_danmu 取代 |
| `inference.py` | 旧版 LLM 调用，被 danmu_ai.py 取代 |
| `screen_capture.py` | 旧版截屏，被 danmu_ai.py 内联取代 |
| `stream_engine.py` | 依赖上述三个已死模块 |
| `stream_processor.py` | stream_engine 配套 |
| `browser_danmu.py` | 浏览器浮层方案，被 Qt 取代 |
| `hanako_link.py` | WebSocket 方案，被 HTTP bridge 取代 |

### 2.4 废弃文件

| 文件/目录 | 数量 |
|-----------|------|
| `*.bak` 备份文件 | 7 个 |
| `archive/` 旧浮层 | 3 个 |
| `__pycache__/` | 30+ pyc |
| `build/` | PyInstaller 中间产物 |
| `test_*.py` | 5 个测试文件 |
| `phase2_test.py`, `phase3_test.py`, `end_to_end_test.py`, `integration_test.py`, `cloud_word_test.py` | 同上 |

---

## 三、清理方案

### Phase 1 — 安全删除（零风险）

**操作**：删除以下文件/目录

```
# 备份文件（7个）
danmu_ai.py.bak
danmu_ai.py.bak2
main.py.bak
main.py.bak2
main.py.bak3
main.py.bak4
voice_danmu.py.bak

# 死代码（7个）
audio_input.py
inference.py
screen_capture.py
stream_engine.py
stream_processor.py
browser_danmu.py
hanako_link.py

# 废弃目录（4个）
archive/
build/
__pycache__/
*.bak 目录通配
```

**预期效果**：减少约 15 个文件，清理 30+ pyc

### Phase 2 — 归档测试文件

**操作**：创建 `tests/` 目录，迁移所有测试文件

```
test_overlay.py           → tests/test_overlay.py
test_visible.py           → tests/test_visible.py
phase2_test.py            → tests/phase2_test.py
phase3_test.py            → tests/phase3_test.py
end_to_end_test.py        → tests/end_to_end_test.py
integration_test.py       → tests/integration_test.py
cloud_word_test.py        → tests/cloud_word_test.py
```

### Phase 3 — 合并重复模块（后续）

**暂不执行，留待下次迭代**

- `danmu_overlay_full.py` + `danmu_widget.py` → 新浮层
- `hanako_link.py` + `hanako_danmu_bridge.py` → 新桥接

---

## 四、待修复问题

### 4.1 统计面板密度计算 Bug

`danmu_stats_panel.py` 的 `_render()` 中：

```python
elapsed = time.time() - self.last_update  # last_update 只在 update_data() 时更新
density = self.total_count / (elapsed / 60)  # elapsed 可能是增量，密度被高估
```

**修复方案**：记录 `start_time`，密度 = `total_count / (now - start_time) * 60`

### 4.2 API Key 安全

`config.yaml` 中 API Key 明文存储。建议：
- 生产环境使用环境变量
- 或加密存储 + 启动时提示输入

### 4.3 弹幕风格配置化

当前 `danmu_ai.py` 的 `_get_prompt_by_style` 只支持 `pi/normal/serious` 三种风格。
用户需求是**多种多样风格可切换**。

**设计方案**：
| 风格名 | 提示词方向 | 适用场景 |
|--------|-----------|----------|
| 皮/玩梗 | 吐槽、玩梗、网络用语 | 默认，通用 |
| 正经描述 | 客观描述画面内容 | 直播教学、代码 |
| 吐槽 | 犀利吐槽、阴阳怪气 | 游戏翻车、奇葩设计 |
| 夸夸 | 真诚赞美、彩虹屁 | 高光时刻、好看画面 |
| 文艺 | 诗意表达、氛围感 | 风景、剧情 |
| 沙雕 | 无厘头、抽象 | 娱乐、整活 |
| 冷幽默 | 简短、反差、一本正经 | 通用 |
| 饭圈 | 尖叫、姨母笑、老婆 | 颜值向 |

**实现方式**：
- `config.yaml` 新增 `danmu_ai_style` 字段（可选值列表）
- 支持运行时切换（托盘菜单或快捷键）
- Prompt 模板化，每种风格独立 prompt 文件

---

## 五、执行记录

### 5.1 备份
- [x] 备份源码到 `danmu-assistant-backup-20260628.zip`（479 MB，含 __pycache__）
- [x] 备份位置：`W:\Games\Hanako\Work\danmu-assistant-backup-20260628.zip`
- [x] 文档：`CLEANUP-PLAN.md`（本文件）

### 5.2 Phase 1 删除 — 已完成 ✅
- [x] 删除 8 个 .bak 文件（danmu_ai.py.bak, .bak2, main.py.bak~.bak4, voice_danmu.py.bak, danmu_overlay_pyqt.py.bak）
- [x] 删除 7 个死代码文件（audio_input.py, inference.py, screen_capture.py, stream_engine.py, stream_processor.py, browser_danmu.py, hanako_link.py）
- [x] 删除 archive/ 目录（3 个旧浮层）
- [x] 删除 build/ 目录（PyInstaller 中间产物）
- [x] 删除 __pycache__/ 目录（30+ pyc）

### 5.3 Phase 2 归档 — 已完成 ✅
- [x] 创建 tests/ 目录
- [x] 迁移 7 个测试文件（test_overlay.py, test_visible.py, phase2_test.py, phase3_test.py, end_to_end_test.py, integration_test.py, cloud_word_test.py）

### 5.4 Phase 3 合并（后续）
- [x] 合并浮层引擎（danmu_overlay_full.py + danmu_widget.py → danmu_overlay_full.py v2.0）
- [ ] 合并 Hanako 桥接（hanako_link.py + hanako_danmu_bridge.py）
- [x] 弹幕风格配置化（支持 9 种风格切换）

### 5.5 本轮执行汇总（2026-06-28）

| 任务 | 状态 | 变更 |
|------|------|------|
| 统计面板密度计算修复 | ✅ | `danmu_stats_panel.py`：`start_time` 替代 `last_update` |
| 浮层引擎合并 | ✅ | `danmu_overlay_full.py` v2.0：预渲染 + 淡入淡出 + 碰撞检测 + 鼠标穿透 |
| 弹幕风格多样化 | ✅ | `danmu_ai.py`：9 种风格（原 3 种），`set_style()` 运行时切换，`list_styles()` 枚举 |
| config.yaml 更新 | ✅ | 新增 `available_styles` 列表 |
| .gitignore 更新 | ✅ | 新增 tests/, reaction_log.json, danmu_stats_*.txt |
| danmu_widget.py 清理 | ✅ | 已合并，删除旧文件 |
| 备份 | ✅ | `danmu-assistant-backup-20260628.zip`（479 MB） |

---

## 六、清理后项目结构（预期）

```
danmu-assistant/
├── main.py                 # 入口（活跃）
├── config.yaml             # 配置（活跃）
├── config.example.yaml     # 配置模板
├── danmu_ai.py             # AI 截屏弹幕（活跃）
├── voice_danmu.py          # 语音弹幕（活跃）
├── asr_engine.py           # ASR 引擎（活跃）
├── danmu_overlay_full.py   # 浮层（活跃）
├── danmu_file_source.py    # 文件弹幕源（活跃）
├── danmu_stats_panel.py    # 统计面板（活跃）
├── danmu_skin.py           # 皮肤（未接入）
├── danmu_history.py        # 历史（未接入）
├── emotion_recognizer.py   # 情绪（未接入）
├── style_advisor.py        # 风格（未接入）
├── keyframe_detector.py    # 关键帧（未接入）
├── window_capture.py       # 窗口截屏（未接入）
├── speaker_diarization.py  # 说话人分离（未接入）
├── hanako_danmu_bridge.py  # Hanako 桥接（未接入）
├── tray_icon.py            # 系统托盘（未接入）
├── scene_builder.py        # 场景构建（未接入）
├── build_exe.py            # 打包脚本
├── config_web.html         # Web 控制台
├── tray_icon.png           # 托盘图标
├── danmu_source.txt        # 文件弹幕源（数据）
├── danmu_history.json      # 历史数据（数据）
├── reaction_log.json       # 反应日志（数据）
├── danmu_stats_*.txt       # 会话统计（数据）
├── DanmuAssistant*.spec    # PyInstaller 配置
├── danmu_assistant.spec    # PyInstaller 配置
├── README.md               # 使用说明
├── 使用说明.md             # 使用说明（中文）
├── CLEANUP-PLAN.md         # 本文件
├── tests/                  # 归档的测试文件（7个）
├── dist/                   # 编译产物（DanmuAssistant.exe）
└── release/                # 发布版
```
├── stream_engine.py        # ⚠️ 待定（依赖已死模块）
├── browser_danmu.py        # ⚠️ 待定（浏览器方案）
├── danmu_source.txt        # 文件弹幕源
├── danmu_history.json      # 历史数据
├── reaction_log.json       # 反应日志
├── DanmuAssistant.spec     # PyInstaller 配置
├── DanmuAssistant_lite.spec
├── build_exe.py            # 打包脚本
├── config_web.html         # Web 控制台
├── tray_icon.png           # 托盘图标
├── README.md               # 使用说明
├── CLEANUP-PLAN.md         # 本文件
├── tests/                  # 归档的测试文件
├── dist/                   # 编译产物
├── release/                # 发布版
└── __pycache__/            # 运行时生成（gitignore）
```

---

*计划 v1.0 · 2026-06-28 · 奥菲莉娅*
