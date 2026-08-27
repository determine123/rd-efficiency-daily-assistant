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

## 真实数据采集

### 从本地 Git 仓库采集

```powershell
python -X utf8 -m app.main `
  --input examples\input.json `
  --repo D:\path\to\your\git-repo `
  --day 2026-08-25 `
  --output reports\2026-08-25.md `
  --metadata-output reports\2026-08-25.analysis.json
```

不传 `--day` 时采集仓库最近提交；传入 `--day` 时采集指定日期提交。

### 从 RSS/Atom 采集新闻

```powershell
python -X utf8 -m app.main `
  --input examples\input.json `
  --rss https://example.com/rss https://example.com/atom.xml `
  --output reports\latest.md
```

单个 RSS 源访问失败不会阻断其他源和日报生成。

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

## LangGraph

安装 `requirements.txt` 后，`app.workflow.build_workflow()` 会自动使用 LangGraph 的 `StateGraph`。未安装 LangGraph 时会使用等价的顺序执行兼容实现，因此规则版功能仍然可用。


### Git

- 忽略 Merge commit；
- 识别 feature、fix、test、docs、refactor、other；
- 根据文件路径映射模块；
- 统计修改热区；
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
