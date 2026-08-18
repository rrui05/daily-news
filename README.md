# Daily News

Daily News 是一个面向前沿资讯调研的中文命令行工具。它调用本机已安装、已登录的 Codex CLI 进行实时网页检索，筛选可靠来源并生成 Markdown 报告。

本项目复用当前计算机上的 Codex 登录账号，不直接调用 OpenAI API，也不要求单独配置 `OPENAI_API_KEY`。

## 功能

运行 `dailynews` 后，可以从五个选项中选择检索范围：

| 选项 | 命令值 | 内容 |
| --- | --- | --- |
| 最新科研进展 | `research` | 中国及全球、多学科的预印本、论文平台、开放评审和科研机构成果 |
| 最新科技企业新闻 | `companies` | 覆盖全球及中国 AI 实验室、模型平台、基础设施、应用、智能体与机器人公司；DeepSeek 和 ByteDance Seed 固定必查 |
| 最新潜力开源项目 | `opensource` | 中国及全球代码托管、模型社区、包仓库和技术社区中的活跃开源项目 |
| 最新市场新闻 | `markets` | 仅覆盖中国（含内地、香港）和美国的宏观、汇率、股票、债券、商品及监管动态 |
| 全部 | `all` | 一次检索以上四个模块，并汇总到同一份报告 |

时间范围由主题是否为空决定：

- 未输入主题，或主题仅含空白字符：检索最近滚动 24 小时内的最新信息。
- 输入了主题：围绕主题及其合理关联方向，检索最近滚动 7 天内的信息。

时间窗口以每次运行的开始时间为基准。严格窗口内没有可靠结果时，报告会如实说明，不会用过期或无法核验的内容凑数。

### 检索逻辑

板块方向由程序根据用户选择直接确定，不交给 Codex 猜测或重新分类。四个具体板块各有一份独立提示词；每次检索只把当前板块的范围、首选来源和排除边界发送给 Codex，再追加用户主题与固定时间窗口。“全部”模式会先由程序拆成四个确定方向，分别检索后合并报告。

科技企业板块采用分组覆盖：逐家扫描主要全球模型公司和中国/东亚 AI 公司，并补充基础设施、应用、智能体、机器人及新兴实验室。DeepSeek 官网/API 更新和 ByteDance Seed 官网/官方仓库属于每次固定检查项。输入主题只会调整检索重点，不会把搜索范围缩成单一公司的白名单；同类竞品、合作伙伴及关键上下游仍会被检查。

科研板块同时按学科和来源分组扫描中国及全球新成果，固定覆盖 arXiv 新稿流、OpenReview、生医/化学预印本和 ChinaXiv；开源板块固定覆盖 GitHub、GitLab、Gitee、Hugging Face 与 ModelScope，并补充主要包仓库及中英文技术社区。市场板块严格限定中国和美国：中国包含内地与香港，其他市场只有在直接影响中美资产时才作为背景。

本机 Codex 安装了用户级 `$search-arxiv` skill，通过无需 API key 的 arXiv Atom API 查询并按精确时间窗口过滤论文。所有开源项目一律不设最低 star、fork、下载量或关注数门槛，这些指标只能作为潜力证据之一，不能作为准入条件。

Codex 只负责在既定方向内扩展主题关键词、寻找来源和整理候选；程序随后再次校验模块、发布时间、URL、来源类型和重复项。用户主题始终作为检索数据处理，不能改变板块和可靠性规则。

## 环境要求

- Python 3.11 或更高版本
- 已安装 Codex CLI
- Codex CLI 已使用本机账号登录
- 可访问互联网

先检查 Codex 是否可用：

```powershell
codex --version
codex login status
```

如果尚未登录，运行：

```powershell
codex login
```

登录流程和 CLI 参数可参考 [OpenAI 官方 Codex CLI 文档](https://developers.openai.com/codex/cli/reference)。Daily News 使用该登录会话进行检索，不需要为本项目另行申请或填写 API key。

## 安装

```powershell
git clone https://github.com/rrui05/daily-news.git
cd daily-news
python -m pip install -e .
```

安装后确认命令可用：

```powershell
dailynews --help
```

## 使用方法

### 交互模式

```powershell
dailynews
```

按提示选择五个模块之一，再输入主题；直接按 Enter 即表示不限主题。

### 命令行参数

也可以通过参数直接指定检索条件：

```powershell
# 最近 24 小时的科研进展；空字符串表示不限主题
dailynews --module research --topic ""

# 最近 7 天内与大模型推理相关的企业新闻
dailynews --module companies --topic "大模型推理"

# 检索全部模块，并把报告写入指定目录
dailynews --module all --topic "AI Agent" --output-dir .\reports

# 临时指定当前 Codex 账号可用的模型
dailynews --module opensource --model <model-name>
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `--module research\|companies\|opensource\|markets\|all` | 指定一个模块或全部模块并跳过菜单；省略时进入交互选择 |
| `--topic <主题>` | 指定主题并跳过主题输入；非空主题使用 7 天窗口，`--topic ""` 使用 24 小时窗口；省略本参数时仍会交互询问主题 |
| `--output-dir <目录>` | 指定 Markdown 报告输出目录，默认是当前目录下的 `reports` |
| `--model <模型名>` | 覆盖本次运行使用的 Codex 模型；省略时沿用本机 Codex 默认设置 |

完整参数以当前安装版本为准：

```powershell
dailynews --help
```

## 来源可靠性

Daily News 遵循“宁缺毋滥”的原则：

- 优先采用论文原文、科研机构、企业公告、项目仓库与 Release、交易所和监管机构等一手来源。
- 权威媒体和社交帖子都可以作为来源，社媒账号不要求必须是官方一手账号；重大或争议事实应尽量交叉核验。
- 每条正式结果应包含来源链接和可核验的发布时间，并按时间窗口筛选。
- 同一事件的重复报道会尽量合并，事实、推断与市场观点应明确区分。
- 无法确认来源、发布时间或关键事实的内容不会被当作可靠消息输出。

实时检索仍会受到来源网站可访问性、发布时间标注方式和 Codex 账号可用能力的影响。请在需要据此作出科研、商业或投资决策前打开原始链接复核；市场模块不构成投资建议。

## 报告格式

报告为 UTF-8 编码的 Markdown 文件，文件名遵循：

```text
主题+模块+时间.md
```

未指定主题时使用“不限主题”作为主题名；选择全部模块时使用“全部”作为模块名。文件名中的 Windows 非法字符会被安全替换，程序不会静默覆盖已有报告。

报告通常包括：

- 本次主题、模块、生成时间和检索时间范围
- 实际覆盖的来源与检索说明
- 按模块组织的新闻或项目条目
- 每条结果的标题、摘要、发布时间、价值说明和来源链接
- 没有符合时效及可靠性要求时的明确说明

默认报告目录及本次生成的具体路径会显示在终端中；可通过 `--output-dir` 改写输出位置。`reports/*.md` 是项目成果，可纳入 Git 版本控制。

## 测试

在项目根目录运行：

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

查看 CLI 帮助并做一次不联网的入口检查：

```powershell
dailynews --help
```

真实检索依赖网络和 Codex 登录状态，耗时可能随主题、模块和来源数量变化。

进程退出码便于自动化判断结果：`0` 表示所选模块全部完成；`1` 表示失败且未生成报告；`2` 表示“全部”模式生成了明确标注的部分报告；`130` 表示用户取消。

## 常见故障

### 找不到 `dailynews` 命令

重新执行 `python -m pip install -e .`，并确认当前 Python 的 Scripts 目录位于 `PATH`。也可以先用 `python -m dailynews --help` 检查包是否已安装。

### 找不到 Codex CLI

运行 `codex --version`。如果命令不存在，请先按 OpenAI 官方文档安装 Codex CLI，并确认其安装目录位于 `PATH`。

### Codex 未登录或登录过期

运行 `codex login status` 检查状态，再用 `codex login` 完成登录。Daily News 使用这个本机登录会话，不会回退到项目内的 API key。

### 检索失败或中途退出

检查网络连接、Codex 账号状态及当前模型是否可用，然后重试。使用 `--model` 后报错时，可去掉该参数以恢复本机默认模型。检索期间可按 Ctrl+C 安全取消；失败或取消不应生成看似成功的报告。

### 报告没有任何条目

这不一定是故障。严格的 24 小时或 7 天窗口内可能没有同时满足时效和可靠性要求的信息。可以输入更明确的主题以使用 7 天窗口，但不建议为了得到更多条目而放宽来源可靠性。

### 无法写入报告

确认输出目录可创建且当前用户拥有写权限，或通过 `--output-dir` 指向其他可写目录。

### Windows 上 pytest 无法创建系统临时目录

如果测试在创建 `pytest-of-...` 目录时报告 `WinError 5`，可把测试临时目录显式放到当前工作区：

```powershell
python -m pytest --basetemp .pytest-tmp
```

## 许可证

本项目采用 [MIT License](LICENSE)。
