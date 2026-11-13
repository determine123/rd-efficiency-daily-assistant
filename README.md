# 研发效能日报生成助手（V0.1）

一个面向研发团队的技术日报生成 MVP。系统接收 Git 提交记录、新闻数据、历史日报风格配置和团队配置，经过确定性分析、证据绑定和规则校验后，生成结构化 Markdown 日报。

## 核心原则

- 事实优先：只使用输入数据中出现的信息。
- 来源可追溯：Git 进展必须绑定 `commit_id`，新闻必须绑定来源或 URL。
- 建议与事实分离：团队建议和明日建议不会伪装成已确定计划。
- 先规则、后模型：V0.1 不依赖 LLM，也可以生成安全日报；后续可将 LLM 接入摘要和风格对齐环节。

## 快速开始

```bash
cd "研发效能日报助手"
python -m app.main --input examples/input.json --output reports/2026-08-25.md
```

Windows PowerShell：

```powershell
cd D:\pi-work\研发效能日报助手
python -m app.main --input examples\input.json --output reports\2026-08-25.md
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 输入文件

输入 JSON 包含：

```json
{
  "current_date": "2026-08-25",
  "team_config": {},
  "git_records": [],
  "news_records": [],
  "historical_reports": []
}
```

参考 `examples/input.json`。

`current_date` 使用严格的 `YYYY-MM-DD` 格式；`team_config` 必须是对象，
`git_records`、`news_records`、`historical_reports` 必须是数组，且数组元素必须是
对象。不符合这些边界时，CLI 会输出可操作的错误并返回退出码 `2`，API 会返回
`422`，不会带着不完整数据继续生成日报。

## 真实数据采集

### 从本地 Git 仓库采集

```powershell
python -X utf8 -m app.main `
  --input examples\input.json `
  --repo D:\path\to\api-repo `
  --repo D:\path\to\worker-repo `
  --day 2026-08-25 `
  --output reports\2026-08-25.md `
  --metadata-output reports\2026-08-25.analysis.json
```

`--repo` 可重复传入以聚合多个本地仓库；重复路径只采集一次，结果按提交时间倒序
合并，并统一限制为最多 200 条。日报的“来源”列会显示仓库目录名与提交号，便于区分
同名提交。单个仓库读取失败不会阻断其他仓库，失败仓库和原因会打印到终端，并写入
metadata 的 `git_collection` 字段；全部仓库都失败时仍生成可审阅日报，但命令返回非零。
证据账本使用“仓库名 + 完整提交 SHA”绑定提交，避免不同仓库的短 SHA 相同导致证据互相覆盖。

不传 `--day` 时采集各仓库最近提交；传入 `--day` 时只采集指定日期的提交。

采集器会为每个文件记录 Git `numstat` 的新增/删除行数；日报会按提交汇总展示
`+新增/-删除 行`。二进制文件的行数不可用，会单独标记为二进制变更。

### 从 RSS/Atom 采集新闻

```powershell
python -X utf8 -m app.main `
  --input examples\input.json `
  --rss https://example.com/rss https://example.com/atom.xml `
  --output reports\latest.md
```

单个 RSS 源访问失败不会阻断其他源和日报生成。CLI 会打印失败源数量及原因；
搭配 `--metadata-output` 时，`rss_collection` 字段会记录请求数、成功数、失败数
和逐源错误，便于排查订阅地址、网络或解析问题。部分源失败仍返回成功；全部源
失败时仍会生成可用日报，但命令返回非零，避免定时任务静默接受空新闻结果。

## LLM 接口

当前支持 OpenAI Chat Completions 兼容接口，可对接本地模型、公司网关或云端 API：

```powershell
$env:LLM_BASE_URL = "https://your-endpoint/v1"
$env:LLM_API_KEY = "your-key"
$env:LLM_MODEL = "your-model"
python -m app.main --input examples\input.json --output reports\llm.md
```

未配置以上三个环境变量时使用确定性规则版，不发送网络请求。LLM 调用失败会自动回退到规则版日报。

## FastAPI 服务

安装依赖：

```powershell
pip install -r requirements.txt
```

启动：

```powershell
python -m app.api
```

接口：

- `GET /health`
- `POST /generate`
- `POST /workflow/invoke`
- `GET /docs`：Swagger 调试页面

两个生成端点共享有界执行槽，默认最多并发处理 4 个任务，可通过
`REPORT_MAX_CONCURRENT_REQUESTS`（1-64）调整。默认等待 120 秒，可通过
`REPORT_REQUEST_TIMEOUT_SECONDS`（0-3600）调整。槽位占满时返回 `503` 和
`Retry-After: 1`；等待超时时返回 `504`。超时仅结束 HTTP 等待，底层任务会在
自身网络超时约束内继续运行并占用槽位，避免超时请求造成无界线程增长。

## LangGraph

安装 `requirements.txt` 后，`app.workflow.build_workflow()` 会自动使用 LangGraph 的 `StateGraph`。未安装 LangGraph 时会使用等价的顺序执行兼容实现，因此规则版功能仍然可用。


### Git

- 按父提交数识别并忽略 Merge commit，即使合并提交使用了自定义标题；
- 识别 feature、fix、test、docs、refactor、other；
- 根据文件路径映射模块；
- 统计修改热区；
- 汇总每个提交的新增/删除行数，并明确标记二进制文件变更；
- 只从明确的 TODO、测试失败、CI 失败、阻塞和未解决信息中提取风险；
- 不自行推断性能提升或业务影响。

### 新闻

- 按标题和正文关键词过滤；
- 识别 AI、LLM、VLM、VLA、Agent、自动驾驶、机器人、世界模型等主题；
- 通过 URL、正文哈希和标题相似度去重；
- 保留来源和 URL；
- 无关新闻不进入日报。

### 质量校验

- 检查代码进展是否有 commit_id；
- 检查新闻是否有来源或 URL；
- 检查来源是否存在于输入数据；
- 检查是否出现未授权数字；
- 检查日报是否包含规定章节；
- 校验失败时命令返回非零状态。

CLI 退出码约定：`0` 表示日报生成且校验通过；`1` 表示日报已生成，但输出校验失败
或所有 Git/RSS 数据源均采集失败；`2` 表示输入文件、字段结构、日期参数或输出写入
存在错误，需要修正后重试。

## 后续演进

1. 接入 GitLab/GitHub API 和 RSS；
2. 增加 ChromaDB/Elasticsearch 检索；
3. 接入公司内部模型或火山云 API；
4. 用 LangGraph 拆分 Git、新闻、生成和校验节点；
5. 增加历史日报风格分析和人工反馈闭环；
6. 增加 FastAPI、定时调度和邮件发送。

## 数据安全

- 示例项目不包含公司内部数据；
- 不要把公司专利、代码、报告和 API Key 提交到个人 GitHub；
- API Key 应通过环境变量传入；
- 生产环境应增加访问控制、日志脱敏和数据保留策略。
