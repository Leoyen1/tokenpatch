# Multi-Model Dev Agent 开发规格文档

## 1. 项目定位

构建一个本地优先的多模型 AI 编程调度工具，用强模型负责需求理解、任务拆分、验收标准和最终审查，用低成本模型负责明确边界的小任务实现、测试和文档草稿，从而降低 AI 编程 token 成本，同时保持可验证的工程质量。

项目第一版不做 SaaS，不做复杂 UI，不托管用户代码。先做一个可在本地项目中运行的 CLI 工具，并配套一个 Codex Skill，使 Codex 能按固定流程调用该工具。

核心卖点：

```text
强模型规划 + 低价模型执行 + 自动测试验证 + 强模型审查
```

目标用户：

```text
独立开发者
小型外包团队
AI 编程重度用户
需要控制 token 成本的创业团队
使用 Codex/Cursor/Claude Code 的开发者
```

非目标用户：

```text
完全不会编程的普通用户
大型企业级 DevOps 团队
需要云端托管代码的团队
追求端到端全自动无审查开发的用户
```

## 2. MVP 目标

MVP 要验证三件事：

```text
1. 同一类开发任务，多模型流程比全程强模型更省成本。
2. 低价模型在明确任务边界下能稳定完成局部代码修改。
3. 强模型 review + 自动测试能拦住主要质量风险。
```

MVP 只支持本地 Git 项目。用户在项目根目录运行 CLI，工具读取需求，生成任务计划，逐个执行任务，跑测试，生成审查报告和成本报告。

第一版必须能完成：

```text
输入自然语言需求
强模型生成结构化任务计划
用户确认任务计划
低价模型执行单个任务并生成 patch
自动应用 patch
运行验证命令
强模型审查 diff 和测试结果
失败后重试或升级强模型
输出最终报告
记录 token/cost 估算
```

第一版暂不支持：

```text
Web UI
多人协作
远程任务队列
云端代码执行
复杂权限管理
自动发布
GitHub PR 自动创建
```

## 3. 推荐技术栈

优先使用 Python，原因是脚本化、文件操作、subprocess、JSON schema、CLI 生态都比较直接。

```text
语言：Python 3.11+
CLI：Typer
配置：pydantic-settings 或 toml
数据校验：pydantic
HTTP：httpx
Patch：git apply / unidiff
状态存储：SQLite
日志：rich + logging
测试：pytest
```

模型接口：

```text
强模型：OpenAI Responses API
执行模型：DeepSeek Chat/Coder API，按 OpenAI-compatible API 适配
```

环境变量：

```text
OPENAI_API_KEY
OPENAI_PLANNER_MODEL
OPENAI_REVIEWER_MODEL
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_EXECUTOR_MODEL
MMDEV_WORKDIR
```

示例默认模型名用配置文件控制，不要硬编码。

## 4. 项目结构

建议仓库结构：

```text
multi-model-dev-agent/
  pyproject.toml
  README.md
  mmdev/
    __init__.py
    cli.py
    config.py
    models/
      __init__.py
      openai_client.py
      deepseek_client.py
      base.py
    planner.py
    executor.py
    reviewer.py
    validator.py
    patcher.py
    git_utils.py
    cost.py
    state.py
    schemas.py
    prompts/
      planner.md
      executor.md
      reviewer.md
  skills/
    multi-model-dev/
      SKILL.md
      scripts/
        mmdev.py
      references/
        task-schema.md
        routing-rules.md
        review-rules.md
  tests/
    test_schemas.py
    test_cost.py
    test_planner_parse.py
    test_patcher.py
```

## 5. CLI 设计

第一版 CLI 命令：

```bash
mmdev init
mmdev plan "为订单列表增加状态筛选"
mmdev run task-001
mmdev validate task-001
mmdev review task-001
mmdev status
mmdev report
```

建议也支持一键流程：

```bash
mmdev auto "为订单列表增加状态筛选"
```

命令职责：

```text
init：在当前项目创建 .mmdev/ 目录和配置文件。
plan：调用强模型生成 tasks.json。
run：调用低价模型执行指定任务，生成 patch 并应用。
validate：运行任务指定的测试/build/lint 命令。
review：调用强模型审查 diff、日志和验收标准。
status：查看任务状态。
report：输出成本、耗时、通过率、风险。
auto：串联 plan/run/validate/review。
```

本地状态目录：

```text
.mmdev/
  config.toml
  tasks.json
  state.sqlite
  logs/
  patches/
  reports/
```

## 6. 核心数据结构

使用 pydantic 定义结构，所有模型输出都必须解析成结构化对象。解析失败时重试一次，仍失败则中止并要求人工处理。

### 6.1 ProjectPlan

```json
{
  "project_summary": "string",
  "assumptions": ["string"],
  "risks": ["string"],
  "tasks": []
}
```

### 6.2 DevTask

```json
{
  "task_id": "task-001",
  "title": "为订单列表增加状态筛选",
  "goal": "string",
  "context": "string",
  "allowed_files": ["src/pages/Orders.tsx"],
  "forbidden_changes": ["数据库 schema", "认证逻辑"],
  "acceptance_criteria": [
    "页面出现状态筛选控件",
    "选择状态后调用 /api/orders?status=xxx",
    "清空筛选后显示全部订单",
    "现有测试通过"
  ],
  "validation_commands": ["npm test", "npm run build"],
  "complexity": "low|medium|high",
  "recommended_executor": "cheap|strong",
  "max_attempts": 2
}
```

### 6.3 ExecutionResult

```json
{
  "task_id": "task-001",
  "changed_files": ["string"],
  "patch_path": ".mmdev/patches/task-001.patch",
  "summary": "string",
  "known_risks": ["string"],
  "needs_human_input": false
}
```

### 6.4 ValidationResult

```json
{
  "task_id": "task-001",
  "command_results": [
    {
      "command": "npm test",
      "exit_code": 0,
      "stdout_tail": "string",
      "stderr_tail": "string"
    }
  ],
  "passed": true
}
```

### 6.5 ReviewResult

```json
{
  "task_id": "task-001",
  "approved": true,
  "findings": [
    {
      "severity": "low|medium|high",
      "file": "string",
      "line": 10,
      "message": "string"
    }
  ],
  "missing_acceptance_criteria": ["string"],
  "recommended_next_action": "approve|retry-cheap|escalate-strong|ask-human"
}
```

## 7. 模型路由规则

Planner 永远使用强模型。

Reviewer 默认使用强模型。

Executor 根据任务复杂度路由：

```text
low：低价模型
medium：低价模型优先，失败一次后强模型审查，失败两次后强模型接管
high：强模型执行或要求人工确认
```

低价模型适用：

```text
单文件或少量文件修改
明确 CRUD
明确 UI 小改动
补测试
文档更新
格式转换
重复性代码生成
```

强模型适用：

```text
架构调整
安全/认证/权限
数据迁移
并发一致性
跨模块隐性 bug
需求不清晰
测试失败原因不明确
低价模型连续失败
```

失败升级规则：

```text
patch 无法应用：重试低价模型 1 次
测试失败且日志明确：低价模型修复 1 次
测试失败且日志不明确：强模型分析
违反 allowed_files：立即回滚并强模型审查
修改 forbidden_changes：立即中止并要求人工确认
同一任务失败 2 次：强模型接管或询问用户
```

## 8. Prompt 要求

### 8.1 Planner Prompt

Planner 必须输出 JSON，不允许输出 Markdown。

要求 Planner：

```text
理解用户需求
读取项目摘要和关键文件
拆成可独立验证的小任务
为每个任务指定允许修改文件
写清 forbidden_changes
写清验收标准
给出验证命令
判断 complexity
选择 recommended_executor
列出假设和风险
```

Planner 不应该：

```text
直接写代码
把大任务拆成模糊任务
让低价模型自由探索全项目
省略验收标准
```

### 8.2 Executor Prompt

Executor 只拿单个任务，不拿全部项目愿景。

要求 Executor：

```text
只修改 allowed_files
不触碰 forbidden_changes
尽量小改动
生成 unified diff
新增或更新必要测试
如果上下文不足，输出 needs_human_input
不要擅自扩大需求
```

Executor 输出必须包含：

```text
patch
changed_files
summary
risks
verification_hint
```

### 8.3 Reviewer Prompt

Reviewer 输入：

```text
任务 JSON
git diff
validation result
相关文件片段
```

Reviewer 需要判断：

```text
是否满足每条验收标准
是否有越界修改
是否有明显 bug
是否需要补测试
是否需要升级强模型
```

Reviewer 不应该只做风格建议，必须优先关注行为正确性、风险、测试缺口。

## 9. Git 与安全策略

MVP 必须保护用户项目。

基本策略：

```text
运行前检查 git status
如果工作区有未提交改动，提示用户确认
每个任务保存 patch
应用 patch 前检查 allowed_files
patch 应用失败不强行覆盖
不自动执行破坏性命令
测试命令必须来自 tasks.json 或用户确认
所有 shell 命令加 timeout
```

建议每个任务使用临时分支或 worktree：

```text
mmdev/task-001
```

MVP 可以先不自动建分支，但必须在报告里明确修改了哪些文件。

## 10. 成本统计

每次模型调用记录：

```text
model
input_tokens
output_tokens
estimated_cost
duration_ms
purpose: plan|execute|review|repair
```

如果 API 没有返回 token usage，就按字符数粗估：

```text
中文约 1.5-2 字/token
英文约 4 chars/token
代码约 3-4 chars/token
```

最终报告输出：

```text
强模型调用次数
低价模型调用次数
估算总成本
如果全用强模型的估算成本
节省比例
任务通过率
重试次数
```

第一版成本报告允许是估算，但要标注 estimated。

## 11. 验收标准

MVP 完成标准：

```text
1. 能在一个真实 Git 项目中运行 mmdev init。
2. 能用 mmdev plan 生成合法 tasks.json。
3. tasks.json 能通过 pydantic 校验。
4. 能用 DeepSeek 执行一个 low complexity 任务并生成 patch。
5. patch 应用前能检查 allowed_files。
6. 能运行任务指定的 validation_commands。
7. 能调用强模型 review diff 和验证结果。
8. 能生成 .mmdev/reports/final-report.md。
9. 能记录每次模型调用的成本估算。
10. 项目自身 pytest 通过。
```

建议用一个示例项目做端到端测试：

```text
examples/todo-app
```

示例任务：

```text
为 todo 列表增加按 completed 状态筛选。
```

预期：

```text
Planner 拆出 1-2 个任务
Executor 修改 UI 和测试
Validator 通过
Reviewer approved
Report 输出成本对比
```

## 12. Codex Skill 设计

技能名称：

```text
multi-model-dev
```

触发描述：

```text
Use when Codex needs to run a multi-model coding workflow that uses a strong model for planning and review, a cheaper model for bounded implementation tasks, and local validation commands to reduce AI coding cost while preserving code quality.
```

SKILL.md 内容应包含：

```text
什么时候使用该技能
必须先检查项目状态
如何调用 mmdev CLI
如何审查 tasks.json
如何处理失败
不要绕过验证
不要让低价模型处理高风险任务
```

技能里的 scripts/mmdev.py 可以只是包装器：

```text
调用已安装的 mmdev CLI
检查配置是否存在
把 Codex 当前需求传给 mmdev plan/auto
```

真正调度逻辑放在主项目 mmdev 包里，不要塞进 SKILL.md。

## 13. 开发阶段规划

### Phase 1: 本地 CLI 骨架

```text
创建 pyproject
实现 config
实现 schemas
实现 CLI init/status
实现本地状态目录
```

验收：

```text
pytest 通过
mmdev init 可创建 .mmdev/config.toml
```

### Phase 2: Planner

```text
实现 OpenAI client
实现 planner prompt
实现 JSON schema 校验
实现 mmdev plan
```

验收：

```text
能生成 tasks.json
无效 JSON 会重试或报错
```

### Phase 3: Executor

```text
实现 DeepSeek client
实现 executor prompt
实现 patch 生成
实现 allowed_files 检查
实现 git apply
```

验收：

```text
能对示例项目生成并应用 patch
越界文件会被拒绝
```

### Phase 4: Validator + Reviewer

```text
实现命令执行器
实现 timeout
实现 validation result
实现 reviewer prompt
实现 review 命令
```

验收：

```text
测试通过时能 approve
测试失败时能给出 retry/escalate 建议
```

### Phase 5: Report + Skill

```text
实现成本统计
生成 final-report.md
创建 Codex Skill
写 task-schema/routing-rules/review-rules
```

验收：

```text
Codex 能根据技能说明使用 mmdev
报告包含成本、任务状态、风险和验证结果
```

## 14. 第一版不要做的事

```text
不要做云端托管
不要做账号系统
不要做复杂 UI
不要支持 10 种模型
不要自动提交 git commit
不要自动运行未知命令
不要让低价模型直接改全项目
不要承诺完全自动开发
```

## 15. 商业化验证指标

开发完成后，用 10 个真实任务测试：

```text
任务完成率
测试通过率
平均重试次数
强模型 token 成本
低价模型 token 成本
总成本
相比全强模型估算节省比例
人工介入次数
Reviewer 拦截的问题数
```

传播用 demo 必须真实：

```text
展示同一个任务的成本对比
展示最终 diff
展示测试结果
展示 review 报告
展示失败任务如何升级
```

可销售版本：

```text
免费版：本地 CLI，支持自带 API Key
付费版：高级路由规则、成本报告、更多模型适配、团队模板
服务版：为小团队搭建 Codex/Cursor + DeepSeek 多模型开发流程
```

首个付费服务建议：

```text
999-4999 元：帮独立开发者/小团队搭建本地多模型 AI 开发流水线
199-999 元/月：维护模型配置、提示词、任务模板和成本报表
```

## 16. 给 Codex 的执行指令

将下面这段作为实际开发请求：

```text
请根据 multi-model-dev-agent-spec.md 实现 MVP。

优先完成 Phase 1 到 Phase 3，确保可以在本地项目中：
1. 初始化 .mmdev 配置。
2. 用强模型生成结构化 tasks.json。
3. 用 DeepSeek 执行 low complexity 任务并生成 patch。
4. 应用 patch 前检查 allowed_files。

要求：
1. 使用 Python 3.11+。
2. 使用 Typer 实现 CLI。
3. 使用 pydantic 定义所有 schema。
4. 所有模型名、API key、base_url 都从配置或环境变量读取。
5. 不要硬编码具体模型名。
6. 所有 shell 命令必须有 timeout。
7. 添加 pytest 单元测试。
8. 每完成一个 Phase 都运行测试。
9. 不要实现 Web UI。
10. 不要自动执行 destructive git 命令。
```

