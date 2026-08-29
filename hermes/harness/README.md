# Hermes Quality Harness

无人值守发布的独立质量层：先跑零成本机械规则，再用 DeepSeek 以 `temperature: 0` 做编辑判断。日报和军火库任一未过门禁，`scripts/server-daily.sh` 都会在构建与发布前退出。

## 判定规则

```text
artifact
  → mechanical rules
  → DeepSeek judge（服务器默认必需）
  → hard_fail 非空：F / 阻断
  → score < 70：携 suggestions 重蒸一次，再判
  → 70–84：B / 可发
  → ≥85：A / 可发
```

日报机械规则覆盖八段、逐字 quote/voice、s/j/h、主题深潜、todo、工程腔、隐私、thread 承接和 newcomer 一致性。Arsenal 覆盖 8–15 条、schema、候选 URL、takeaways 和 threads 命中率。

DeepSeek judge 只判断机械规则难以判断的四项：深潜是否真的越过复述、语气是否判对、文风是否像编辑而不是报表、是否真正接住上一期。模型输出不会替代 hard gate。

## 本地评分

无 key 时必须显式使用 `--mechanical-only`，输出会标明 `judge_mode: mechanical-only`，不会伪造 LLM 分：

```bash
python3 hermes/harness/judge.py site/content/ledgers/2026-08-23.json \
  --kind ledger \
  --transcript hermes/ledger/sample/transcript.txt \
  --date 2026-08-23 \
  --mechanical-only

python3 hermes/harness/judge.py site/content/arsenal/2026-08-23.json \
  --kind arsenal \
  --candidates hermes/harness/tests/golden/arsenal-candidates.jsonl \
  --previous site/content/ledgers/2026-08-23.json \
  --date 2026-08-23 \
  --mechanical-only
```

服务器使用 `--require-llm`；无 key、API 失败或 judge schema 错误都会形成 hard fail。`DEEPSEEK_JUDGE_MODEL` 可单独指定 judge 模型；temperature 固定为 0，`DEEPSEEK_SEED` 可选。

## 发布日志与健康面

`health.py combine` 把日报和军火库判定合成 `/opt/xfsite/logs/quality-YYYY-MM-DD.json`，包含：

- 总分、A/B/F、hard/soft/suggestions；
- 两份 artifact 的完整判定；
- 重蒸次数、耗时、DeepSeek token 用量；
- artifact prompt 与 judge prompt 版本。

失败时同时覆盖 `/opt/xfsite/logs/ALERT`，并向 `/opt/wechat-archive/export.log` 追加一行。`health.py aggregate` 汇总最近 14 天到 `site/public/health/daily.json`；本地无日志时输出空数组而不是伪造健康记录。

日报转换后由 `stamp.py` 写入：

- `credits.prompt_version`
- `credits.model`
- `credits.quality_grade`
- `credits.self_check_score`
- `quality_gate`
- 可见 footer：`本期自检 78 分 · B`

## Prompt 版本

运行时 prompt 位于 `hermes/prompts/`：

- `ledger-extract-v3.md`
- `ledger-skeleton-v3.md`
- `ledger-fill-v3.md`
- `arsenal-distill-v3.md`
- `judge-v1.md`

每个文件都有 frontmatter `prompt_version`。Ledger 成品写 `prompt_version: ledger-v3`，转换后再进入 `credits.prompt_version`；Arsenal v3 版本进入质量日志。修改 prompt 后必须跑黄金回归。

## 黄金回归

```bash
python3 -m venv /tmp/hermes-harness-venv
/tmp/hermes-harness-venv/bin/pip install -r hermes/harness/requirements-dev.txt
/tmp/hermes-harness-venv/bin/pytest hermes/harness -q
```

黄金集包含：

- 08-23 transcript + 当前 Ledger 结构指标；真实产物指标偏差不得超过 40%；
- 固定 30 条 Arsenal 候选，真实 08-23 输出必须保持 8–15 条、URL 全部命中且 threads 命中率不退化；
- dry-run 仍必须通过当前 Ledger schema 和逐字硬检查。

## 服务器安装

运行时代码没有第三方依赖：

```bash
sudo install -d -m 0755 /opt/hermes-harness
sudo rsync -a hermes/harness/ /opt/hermes-harness/
sudo chmod +x /opt/hermes-harness/{judge.py,health.py,stamp.py}
```

`scripts/server-daily.sh` 设置 `HERMES_PROMPTS_DIR=$REPO/hermes/prompts`，因此三个 Hermes 组件始终读取仓库正本 prompt。军火库先写 quality staging；日报先判 `materials/.../content.json`，通过后才转成站点 Ledger。最终合并门禁未通过时不会执行站点 build、rsync、commit 或 push。
