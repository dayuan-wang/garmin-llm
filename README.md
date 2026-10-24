# Garmin Learning MCP · 0.3.0

自己的 Garmin 数据接口、训练日志和分析工具。通过本地 stdio 接入 GPT／Claude，服务端无需 LLM API key。

本版提供 **78 个内置 MCP 工具**，覆盖截至 2026-10-23 核对的 Garmin Personal API **25 个 JSON GET 接口 + 1 个活动 ZIP 下载接口**。覆盖的是公开接口目录；实际数据取决于账户权限、设备、记录和 Garmin 返回内容，不等于 Garmin Connect 页面上的所有功能。

## 独立 JSON 接口（v0.3.0）

这里的“接口”是通过本地 stdio 调用的 MCP 工具，不是 HTTP REST URL。每个工具有独立名称和输入 JSON Schema，全部工具同时返回 JSON 文本及 MCP structuredContent，并声明 outputSchema。完整机器可读目录在 [docs/tool-schemas.json](docs/tool-schemas.json)，运行 `python examples/export_schemas.py` 可重新生成。

每个受支持健康数据集都有独立工具，例如 `get_stress`、`get_hydration`、`get_hrv`、`get_spo2`、`get_weight`、`get_sleep_summaries`。`get_steps(date)` 保持兼容，步数历史使用 `get_steps_history(start_date, end_date)`。呼吸、热量、强度分钟、movement 和心率摘要还有独立的 daily-summary 字段视图；它们保留原始子对象，并非新增 Garmin 上游 API。

31 个内置运动工具使用 `get_<Garmin typeKey>_workouts` 命名，覆盖跑步、骑行、泳池／公开水域游泳、力量、HIIT、室内有氧、篮球、抱石等。`list_workout_types` 列出当前工具。每个工具精确匹配类型：普通跑步不混入 trail_running。它们读取已完成活动，结构化 workout 步骤仍用 `get_activity_workouts(activity_id)`。

Garmin Personal API 没有在本项目核实的完整类型目录接口，因此内置类型不是“所有 Garmin 类型”的保证。调用 `discover_workout_types` 扫描你指定日期的历史，可以为每个新出现的合法 typeKey 注册独立工具；仅类型键保存在本机数据库，不保存活动内容。会发送工具列表更新通知，客户端未刷新时重连。分页未完成时不会声称覆盖全部历史。

```json
{"name":"get_running_workouts","arguments":{"start_date":"2026-10-01","end_date":"2026-10-22"}}
```

```json
{"name":"get_stress","arguments":{"start_date":"2026-10-01","end_date":"2026-10-22"}}
```

```sh
.venv/bin/python examples/client.py --tool get_strength_training_workouts --arguments '{"start_date":"2026-10-01","end_date":"2026-10-22"}'
.venv/bin/python examples/client.py --live --tool discover_workout_types --arguments '{"start_date":"2026-01-01","end_date":"2026-10-23","max_records":1000}'
```

## 能做什么

| 功能 | MCP 工具 |
|---|---|
| 查询支持的数据和参数 | `list_data_types` |
| 原样读取全部受支持 JSON 数据 | `get_garmin_data` |
| 常用单日查询 | `get_steps`, `get_sleep`, `get_heart_rate` |
| 查运动历史、单次训练详情、关联 workout | `get_activities`, `get_activity` |
| 下载原始活动 ZIP，不解压 | `download_activity` |
| 睡眠、HR/HRV、步数、压力、Body Battery 和运动汇总 | `get_health_overview` |
| 最近 7 天和此前 7 天对比、分运动类型的距离/时长/配速 | `analyze_training` |
| 补充健身动作、重量、次数、RPE 和训练感受 | `log_workout`, `list_workout_logs` |
| 查看同一动作的负荷、训练量和估算 1RM 变化 | `analyze_strength_progress` |
| 保存目标、时间安排、器械、经验和偏好 | `save_coach_profile`, `get_coach_profile` |
| 为个性化跑步／健身计划准备数据和偏好 | `prepare_coaching_context` |
| 保存和读取 GPT／Claude 生成的计划 | `save_training_plan`, `list_training_plans` |
| 生成本地 HTML dashboard 和 JSON 快照 | `create_dashboard` |

训练复盘：模型读取活动详情、睡眠/HRV、你补充的日志后解释数据。训练计划：模型根据 `prepare_coaching_context` 返回的证据和目标生成具体日程，再按你的要求保存。MCP 本身执行取数、统计和存储，不内置另一个付费模型，也不会独立生成医学结论或 Garmin 专有 readiness 分数。

## 先离线运行

项目已有 `.venv` 时直接运行客户端。重新安装依赖时：

```sh
uv venv --python 3.10
uv pip sync --python .venv/bin/python requirements.lock
.venv/bin/python examples/client.py
```

使用 `uv pip sync`，本项目没有 `uv.lock`。固定直接依赖：`mcp==1.27.1`、`python-dotenv==1.2.2`、`pydantic==2.13.4`。Garmin HTTP 使用标准库，无第三方 Garmin SDK。

```sh
.venv/bin/python examples/client.py --tool list_data_types
.venv/bin/python examples/client.py --tool analyze_training --arguments '{"start_date":"2026-10-01","end_date":"2026-10-22"}'
```

默认 demo 使用合成数据，结果带 `source: demo`，不访问 Garmin、不读取密钥、不写入真实训练日志。Demo dashboard 也会明确标注合成数据。通信使用真实 MCP 子进程和 JSON-RPC。

## 查询真实数据

保留项目原有 `.env.local`：

```dotenv
GARMIN_PERSONAL_API_KEY=你的实际密钥
```

密钥优先级：环境变量 → 项目 `.env.local` → 旧版 `~/.config/garmin-mcp/api-key`。从源码位置定位配置，不依赖启动目录。密钥不作为 MCP 参数、不写入工具结果。旧的隐藏输入命令 `python -m garmin_mcp auth` 仍可使用。

```sh
.venv/bin/python examples/client.py --live --date 2026-10-22
.venv/bin/python examples/client.py --live --tool get_sleep --arguments '{"date":"2026-10-22"}'
.venv/bin/python examples/client.py --live --tool get_activities --arguments '{"start_date":"2026-10-01","end_date":"2026-10-22"}'
.venv/bin/python examples/client.py --live --tool get_health_overview --arguments '{"start_date":"2026-10-01","end_date":"2026-10-22"}'
.venv/bin/python examples/client.py --live --tool create_dashboard --arguments '{"start_date":"2026-10-01","end_date":"2026-10-22"}'
```

Dashboard 返回 HTML/JSON 的绝对路径，浏览器打开 HTML 即可。它是离线快照，不是后台自动刷新的网页应用。数据文件在项目 `.data/`，无需外部资源或公开托管。

认证过程是 Personal API key → 短期 access token → GET。一个工具操作内复用 token，下一次操作重新读取配置。每次 HTTP 超时 15 秒，不自动重试；固定 Garmin 官方域名、拒绝重定向、隐藏原始错误响应体。真实失败不会回退为 demo。原始 JSON 上限 8 MB、ZIP 上限 32 MB，超限明确报错。

## 支持的数据目录

通过 `get_garmin_data(dataset=...)` 读取，保留原始字段：

| 参数类型 | dataset |
|---|---|
| `start_date`, `end_date`，也可单独传 `date` | `steps`, `stress`, `hydration`, `weight_goals`, `weight`, `weight_entries`, `sleep_summaries`, `body_battery`, `daily_summaries`, `hrv_summaries`, `wellness_activities` |
| `date` | `sleep`, `heart_rate`, `daily_summary`, `hrv`, `food_logs`, `spo2`, `fitness_age`, `menstrual_summary` |
| `date` 和 `today_date` | `menstrual_day` |
| 无额外参数 | `profile`, `heart_rate_zones` |
| `activity_id` | `activity`, `activity_workouts` |
| 可选日期对、`start`, `limit`, `activity_type` | `activities` |

- 日期格式严格为 `YYYY-MM-DD`，范围包含首尾。保留 Garmin 返回的 calendarDate；睡眠日期以 Garmin 归属日期为准。
- 原始步数／压力查询每次最多 28 天，其他原始范围查询最多 31 天。独立健康工具最多接受 366 天并自动分段；综合分析最多 90 天，按各接口上限拆分。
- 活动查询最多 366 天，每页最多 100 条。`get_activities` 自动分页，默认最多 500 条、可设 1000 条。`complete=false` 表示不能声称已读取全部历史；缩小日期或通过原始工具继续分页。
- 缺失、负数占位符和非有限值不用于统计；有效的 0 保留。每个指标报告实际覆盖天数。接口出错、限流、权限不足、部分成功都显式报告。
- 原始数据单位保持 Garmin 原样；汇总明确标注 km、分钟、bpm、ms、小时。跑步综合配速按总时长/总距离计算，只使用同时有时长和距离的记录。
- 食物、经期等可选数据仅在相关请求中调用，不自动加入总览。
- 新字段自动保留；新增官方接口需要更新允许列表，不允许模型自行构造任意 URL。

## 力量训练与个人计划

可以直接对接入后的模型说：

> 记录 2026-10-22 的深蹲：总重量 60 kg，3 组，每组 5 次，RPE 7。备注：最后一组速度慢。记录 ID 用 squat-20261022。

每组是一个独立 item；重量默认是该动作总外加重量。哑铃每只重量、自重或辅助重量要明确说明。工具请求示例：

```json
{
  "record_id": "squat-20261022",
  "workout": {
    "date": "2026-10-22",
    "sport": "strength_training",
    "sets": [
      {"exercise":"squat","weight":60,"unit":"kg","reps":5,"rpe":7},
      {"exercise":"squat","weight":60,"unit":"kg","reps":5,"rpe":7},
      {"exercise":"squat","weight":60,"unit":"kg","reps":5,"rpe":7}
    ],
    "notes": "最后一组速度慢"
  }
}
```

如果对应 Garmin 活动，可加 `activity_id` 关联。日志不会重新计入 Garmin 的运动距离或时长，避免重复统计。进步分析统一换算 kg；自重、辅助重量和外加重量分开。1RM 使用 Epley 公式，仅对 1–10 次外加负重组给出估算，不能当实测最大力量。保持相同动作命名、器械、动作幅度和重量记录方式才适合比较。

本地 SQLite：`.data/coach.sqlite3`。同一个 ID、相同内容重复保存不会重复记录；修改已有内容需要 `replace=true`，保留旧版本。训练计划默认 `draft`，只有你接受后才标记 `accepted`。日志、偏好和计划都不会上传回 Garmin。

可尝试：

- “分析过去 28 天睡眠、静息心率、HRV 和跑步趋势，先报告数据覆盖情况。”
- “复盘活动 123456789，结合前一晚睡眠和我的训练感受。”（替换真实 ID）
- “比较我最近一个月的深蹲训练，分开比较重量和训练量。”
- “保存我的目标：提高 5K 表现，每周二、四、日可跑，每次 45 分钟。”
- “结合过去 28 天和我的偏好制定下周跑步计划，说明依据和缺少的信息。”
- “把这个计划保存为草稿。”
- “生成最近 28 天 dashboard。”

## 更新 ChatGPT／Claude 接入

现有启动命令和路径不变。插件启动脚本始终运行这个项目源码，因此增加工具后需要**重新启动 MCP 连接并开启新会话**，通常不需要重填密钥或路径。旧会话可能保留旧工具列表；以新会话能列出至少 78 个工具作为发现检查。

本地插件源目录 `chatgpt-plugin/` 中的描述和版本已更新到 0.3.0。已安装的旧插件界面描述可能仍显示“步数”；这不改变它启动项目源码的方式。如需刷新安装元数据，在终端运行：

```sh
python3 examples/configure_plugin.py
codex plugin marketplace add "$PWD/chatgpt-plugin"
codex plugin add garmin-learning@garmin-local
```

插件使用内部相对命令 `./scripts/start-garmin`；不要改成 manifest 中的绝对命令路径。脚本先读取 GARMIN_MCP_PROJECT 或本机生成的 .project-path，再定位项目 Python。移动项目时重新运行 examples/configure_plugin.py 并重装插件；.project-path 不提交 Git。

Claude Desktop 可将以下条目合并进 `mcpServers`，替换路径后重启：

```json
{
  "mcpServers": {
    "garmin-learning": {
      "command": "/ABSOLUTE/PATH/garmin-llm/.venv/bin/python",
      "args": ["-m", "garmin_mcp"],
      "env": {"PYTHONPATH": "/ABSOLUTE/PATH/garmin-llm"}
    }
  }
}
```

本地运行的是 MCP 服务。工具结果被发送给 GPT／Claude 时，相应模型服务会处理这些结果；这不等于模型也在本机运行。没有添加第三方 Garmin MCP 中转服务器。

## 学习路线与验证

| 文件 | 职责 |
|---|---|
| `garmin_mcp/catalog.py` | 数据允许列表、日期与参数校验 |
| `garmin_mcp/garmin.py` | 配置、认证、HTTP 和错误清理 |
| `garmin_mcp/health_tools.py` / `workouts.py` | 独立健康接口、运动类型工具与发现机制 |
| `garmin_mcp/data.py` | 分段、分页、部分失败与合成 fixtures |
| `garmin_mcp/analysis.py` | 可解释的统计，不调用模型 |
| `garmin_mcp/journal.py` | Pydantic 输入模型、SQLite 和修改历史 |
| `garmin_mcp/dashboard.py` | 转义后的离线 HTML 与 JSON 快照 |
| `garmin_mcp/server.py` | `FastMCP` 工具、JSON Schema、使用说明 |
| `examples/client.py` | 初始化、发现工具、调用任意工具 |
| `tests/` | HTTP 替身测试、本地持久化与真实 stdio 协议测试 |

普通 Python 函数 → `@server.tool()` → 类型标注/docstring 自动生成 schema → 客户端 `list_tools` 发现 → `call_tool` 校验并执行 → 模型解释结果。模型 API 和 MCP 协议是两个不同层次。

服务的 stdout 专用于协议，不要向 stdout 打印日志；日志写 stderr。直接启动服务后等待是正常的，它在等客户端消息。

```sh
.venv/bin/python -m unittest discover -s tests -v
```

目前测试使用合成数据和 HTTP 替身，不访问真实 Garmin。用户已在本机验证旧版步数真实链路；本次新增接口尚未用真实账户逐项验收。请从睡眠、活动列表、综合总览开始，与 Garmin Connect 同日记录核对。API 文档覆盖不代表每个设备都返回对应字段。

尚未实现：后台同步、多设备云端部署、交互式长期托管 dashboard、FIT 二进制解析、向 Garmin 写入训练计划或自动安排提醒。现有 dashboard 是可运行快照，训练复盘和个性化计划通过接入的 LLM 完成。

旧 `garmin-llm-starter.zip` 不代表本版源码，不要用它覆盖当前项目。

## 官方参考

- [Garmin Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/)
- [Garmin Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
- [Garmin 官方参考客户端](https://github.com/garmin/connect-personal-api-python)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## Dashboard design update

Dashboard 现在使用内嵌 CSS/JavaScript，打开单个 HTML 即可离线交互，无 CDN 或外部字体请求：

- 主图对齐健康指标与训练日期，使用独立纵轴，缺失日期断线。
- 切换睡眠、HRV、静息心率和步数；选择完整周期、最近 14 天或 7 天。
- 日期筛选同步更新汇总、图表、运动分布和活动列表；最近两周对比固定，并明确标注日期。
- 活动按运动类型筛选；日志和力量进步保留在独立区域。
- HTML 仅嵌入显示需要的活动字段，不包含账户标识或 GPS 坐标。JSON 快照仍保留原始报告数据。
- 支持窄屏布局、键盘焦点和减少动态效果设置。页面不会生成新的 readiness 分数。

设计参考：[Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)。
浏览器截图验收受当前本机权限限制；交互计算另有无需浏览器的 JavaScript 检查：

```sh
node tests/dashboard_interactions.cjs
```

参考项目比较（2026-10-23，根据各项目 README，未安装或执行第三方代码）：

- [Taxuspt/garmin_mcp](https://github.com/taxuspt/garmin_mcp)：基于 `python-garminconnect`，README 宣称 110+ 工具，覆盖活动修改、训练下发、设备/装备、营养、路线，以及 FIT 和骑行分析。认证使用 Garmin 登录及缓存 token，和本项目 Personal API key 不是同一方式。
- [Mason-Levyy/garmin-personal-mcp](https://github.com/Mason-Levyy/garmin-personal-mcp)：官方 Personal API 的只读封装，支持每日汇总、日期分段、按需返回采样数组和更广的活动筛选条件。与本项目接入方式更接近。
- 后续优先参考：按接口配置日期上限、原始采样数据按需返回、更丰富的活动筛选。Taxuspt 的高级指标与写入能力不能直接当作官方 Personal API 已支持的功能。

## GitHub 发布与测试

源码发布在 `dayuan-wang/garmin-llm` 私有仓库，版本标签 `v0.3.0`。密钥、`.project-path`、健康快照及数据库不会提交。

当前 GitHub 授权不包含 workflow 权限，所以自动测试配置保存为 `docs/github-actions-tests.yml` 模板，尚未在 GitHub Actions 启用。需要启用时，由有 workflow 权限的账户把它放到 `.github/workflows/tests.yml`。本地验证命令：

```sh
.venv/bin/python -m unittest discover -s tests -v
node tests/dashboard_interactions.cjs
```

2026-10-24 验证：41 项 Python 测试和 JavaScript 交互检查通过；真实账户抽查 `get_hrv`、`get_stress`、`get_running_workouts` 均成功。其余路由经过替身测试，尚未逐个用真实账户验证。
