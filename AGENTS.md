# Skills

本文件仅负责技能发现与路由，不重复定义技能中的具体流程、规则或实现细节。当任务命中下列任一场景时，先读取对应的 `SKILL.md`，再按技能文件中的流程执行。一个任务可以同时适用多个 Skill；应读取所有相关 Skill，并综合遵循其约束。

| Skill | 适用场景 | 路径 |
|---|---|---|
| `repository-workflow` | 提交/PR、安全检查、PowerShell Markdown 引号、测试与日志入口、批量改码验证 | `.agents/skills/repository-workflow/SKILL.md` |
| `deploy` | 提交完成改动、计算并创建 stable/beta/alpha tag、推送发布远端 | `.agents/skills/deploy/SKILL.md` |
| `use-local-venv` | 运行 Python、测试、lint、依赖检查或安装，统一使用 uv 与仓库 `.venv` | `.agents/skills/use-local-venv/SKILL.md` |
| `ok-script-tasks` | 创建、修改、注册或审阅 `BaseTask` / `TriggerTask` 任务 | `.agents/skills/ok-script-tasks/SKILL.md` |
| `ok-script-codegen` | 根据描述或截图生成任务 `run()` 自动化代码 | `.agents/skills/ok-script-codegen/SKILL.md` |
| `ok-script-i18n` | gettext UI 文案、PO/MO、收集池防污染与目录冲突合并 | `.agents/skills/ok-script-i18n/SKILL.md` |
| `ok-config-migration` | 修改持久化任务配置的键名、值格式或所属任务，并迁移账号覆盖数据 | `.agents/skills/ok-config-migration/SKILL.md` |
| `ok-script-pr-review` | 核实与处置 CodeRabbit PR 审阅、等待本轮审阅、处理限流、线程状态核对（不自行解析线程） | `.agents/skills/ok-script-pr-review/SKILL.md` |
| `pr-scope-responsibility` | 规划或审阅 PR 职责边界、判断是否需要拆分、核对标题/描述与实际 diff 范围一致性 | `.agents/skills/pr-scope-responsibility/SKILL.md` |
