# B2B Lead Agent Skill 测试报告：儿童玩具行业

测试时间：2026-06-21 23:40 CST

GitHub 仓库：https://github.com/nvnmvm/b2b-lead-agent

## Skill 功能说明

`b2b-lead-agent` 是一个面向 B2B 外贸/供应链开发信的 Codex Skill，核心功能是把公开公司线索转成可人工审核的潜在客户与邮件草稿。它不会默认发送邮件，发送动作需要显式人工确认。

主要能力：

- 初始化本地运行目录、配置文件和 SQLite 数据库。
- 从 CSV 导入目标公司线索。
- 扫描公司网页，提取公司摘要、联系人、邮箱和公开证据。
- 按目标国家、行业、客户类型、产品相关性、职位和邮箱可信度评分。
- 只对合格线索生成 80-150 词左右的冷邮件草稿。
- 导出 `xlsx`、`json`、`.txt`、`.eml`，方便人工复核。
- `approve-send` 默认只做审批预览；不带 `--confirm` 时不会发送。

## GitHub 验证

- 仓库已创建为 public：`nvnmvm/b2b-lead-agent`
- 远端仓库根目录包含 `SKILL.md`，可作为 Codex Skill 直接下载安装。
- 通过 GitHub 重新安装到 Codex 技能目录：
  `/Users/anpengxin/.codex/skills/b2b-lead-agent`
- 重新安装后的单元测试结果：`23 passed`

## 本次测试配置

行业场景：儿童玩具、教育玩具、玩具进口商/分销商/零售商。

测试公司：

- HappyKids Toys GmbH：德国教育玩具/木制玩具分销商。
- BrightPlay Toys：德国儿童玩具进口商与零售商。

测试输入目录：

`/tmp/b2b-lead-agent-toy-test`

发送模式：

- `email.mode`: `draft_only`
- `email.require_manual_approval`: `true`
- 未执行 `approve-send --confirm`

## 执行结果

命令链路全部成功：

- `init`: 成功，创建数据库和默认配置。
- `search`: 成功，导入 2 家公司。
- `scan`: 成功，扫描 2 家公司网页。
- `score`: 成功，处理 2 条线索，合格 2 条。
- `draft`: 成功，生成 2 封邮件草稿。
- `export`: 成功，导出 2 条线索和 2 封草稿。
- `status`: 成功，错误数 0，未解决错误 0。
- `approve-send`: 成功进入人工审批预览，`processed = 0`，未发送邮件。

最终状态：

- companies: 2
- contacts: 2
- leads: 2
- email_drafts: 2
- lead_statuses: `DRAFTED: 2`
- errors: 0
- unresolved_errors: 0

评分结果：

- BrightPlay Toys：97，`HIGH`
- HappyKids Toys GmbH：100，`HIGH`

审批预览结果：

- lead_id: `lead-brightplaytoys-test-martin-keller-brightplaytoys-test`
- recipient: `martin.keller@brightplaytoys.test`
- subject: `Quick question about BrightPlay Toys`
- requires_approval: `true`
- processed: `0`
- mode: `draft_only`

## 导出文件

生成文件位于：

`/Users/anpengxin/.codex/skills/b2b-lead-agent/output`

关键文件：

- `leads_20260621_153946.xlsx`
- `drafts_20260621_153946.xlsx`
- `leads_20260621_153946.json`
- `run_summary_20260621_153946.json`
- `draft_review/lead-happykidstoys-test-laura-schneider-happykidstoys-test.txt`
- `draft_review/lead-happykidstoys-test-laura-schneider-happykidstoys-test.eml`
- `draft_review/lead-brightplaytoys-test-martin-keller-brightplaytoys-test.txt`
- `draft_review/lead-brightplaytoys-test-martin-keller-brightplaytoys-test.eml`

## 质量观察

- GitHub 下载安装后的 Skill 可直接运行单元测试和功能流程。
- 儿童玩具行业样例能完成导入、扫描、评分、草稿、导出和审批预览。
- 邮件草稿个性化内容优先使用公司摘要，不再把联系人邮箱片段作为正文个性化证据。
- 全流程未真实发送邮件，符合本次测试要求。

结论：本次 GitHub 发布版通过 Codex 安装测试和儿童玩具行业功能测试。
