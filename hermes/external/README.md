# 外部知识自动精选

把公开订阅源转换为有出处的中文精选与事件日报。入口 `/sources/`；Agent 读取 `/data/external-curated.json` 或现有 `/api/public/learning`、RSS 和 MCP 学习目录。微信日报仍走原有管线。

顺序为 RSS/Atom 采集 → 模型预筛 → 同一标准两次互盲评分 → 中文标题摘要 → 原文核对 → 事件归组 → 独立归组复核 → 热度和日报。只借鉴 AIHOT 的流程思路，自行实现，未复制其代码或提示词：https://github.com/KKKKhazix/AIHOT 。

`config/external-curation.json` 定义来源等级、独立发布方、门槛、日期窗口、单次/每日调用预算和重试限制。提示词在 `hermes/external/prompts/`。两次评分使用同一模型的独立请求，第二次不接收第一次结果，不宣称多模型共识。评分取两次均过线且分歧未超限；中文内容需逐字原文依据并通过另一次事实核对。

采集范围目前为已配置的官方 RSS/Atom。读取发布方官方网页正文，提取有限长度片段供模型核对，不执行网页脚本。只允许已配置发布方域名、www 别名及显式 `articleHosts`、HTTPS 和公开 IP；DeepMind 的官方跳转 `blog.google` 已显式登记；重定向同样检查，限制响应大小、时间和文字长度。正文不可用且订阅摘要为空时留待重试；有摘要则交给同一套评分判断信息是否充分，并标注依据类型。未接入需要单独账号的 X、公众号。媒体与社区来源可在来源配置与来源等级中明确加入，不能默认当作官方。

## 执行

```sh
bash scripts/ops/refresh-external-sources.sh
python3 scripts/ops/curate_external_sources.py --state /path/to/state.db
python3 scripts/ops/curate_external_sources.py --state /path/to/state.db --retry-failed
```

复用现有 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`，可用 `EXTERNAL_CURATION_MODEL` 单独指定模型。发布脚本仅在密钥尚未加载时从现有 `HERMES_ENV_FILE` 加载环境，不输出值。只接受 DeepSeek 官方接口，不设置新中转。缺少密钥、模型故障或无效 JSON 都留待重试，不制造成功结果。

默认状态库 `/opt/xfsite/data/external-curation/state.db`，与 `xf.db` 分开。锁文件拒绝并发；阶段缓存按输入、模型、提示词和政策指纹隔离；调用前预扣次数，失败也计入预算；格式或逐字依据校验失败时有一次受预算约束的纠正机会，仍失败才入重试队列；中断后可重放。达到当天重试上限时状态持续显示失败，下一天自动恢复重试；修复提供方后也可用 `--retry-failed` 立即重置次数，已成功阶段与预算仍保留。政策更新重评已有资料。

## 自动运行与发布

三个标准发布入口在构建前刷新来源并执行精选。`install-external-curation-cron.py --expect-commit <完整SHA> --apply` 安装单独的每小时发布任务，默认每小时第17分钟，修改分钟需显式参数；只管理自己的 cron 文件，不改微信任务。它使用已有发布锁、Git 快进检查、保留旧哈希 chunk 的静态发布流程。发生资料处理失败时发布可用内容与失败状态，页面明确显示未完成。

安装前默认只打印任务；覆盖自己管理的旧任务前保存备份。回滚自动任务可移走 `/etc/cron.d/ai325-external-curation`，再按既有站点发布回滚流程恢复旧代码与静态快照；不删除状态库或业务库。

## 数据口径

- 热度按配置窗口内的独立发布方计数，并按半衰期衰减；Google 的两个 feed 共用发布方，不重复抬高热度。没有基线的事件标记新出现，有足够早的快照后才比较趋势。
- 日报按北京时间分日，每事件每天一条，跨日只收有新进展的报道。当天标记持续更新；有待处理或失败则历史成刊显示部分状态。迟到资料引发显式修订，重放不增加修订号。
- 未知发布日期保留在原始来源页，不用抓取时间冒充。未来日期暂缓，旧资料超出窗口不冒充当天新闻。
- 原文内容、模型响应都作为不可信资料，不能触发 shell、文件或服务操作。公开文件只有通过筛选的公开资料及运行计数，不包含凭据或微信群记录。

验证命令：`python3 -m unittest app.test_external_curation app.test_external_sources -q`。离线测试与真实提供方、生产发布、浏览器验收分别记录，不混为同一份证据。
