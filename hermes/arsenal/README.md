# Hermes Arsenal

每天从公开信源收集最多 120 条候选，再用 DeepSeek **先筛选、后蒸馏**出 8–15 条适合「🌱人民需要AI_智能体先锋队」的知识条目。

## 文件与数据流

```text
sources.yaml
  → collect.py
  → candidates/YYYY-MM-DD.jsonl
  → distill.py + site/content/ledgers/*.json 的 threads
  → site/content/arsenal/YYYY-MM-DD.json
```

- 单个信源的主地址失败时会依次尝试 RSSHub / Google News RSS 备用镜像；主备都失败才记 `[fail]`，其余源继续。所有源都无结果时才整体失败，并保留旧候选。
- URL 会去跟踪参数、fragment 与重复斜杠；再按 URL 和近似标题去重。
- DeepSeek 输出的硬门槛只有：schema 字段齐全且类型正确、`kind` 在枚举内、`source.url` 来自候选集、作者/日期不得脱离候选信息、`takeaways` 为 3–5 条。硬门槛失败时，重试会带上上一次完整输出和具体错误请模型定点修复。
- `one_line` 长度、`why` 句数/句号、`quote` 非空等软规则会自动截断、补齐或清空，并记入 `[warn]` 与结果摘要，不会拒绝整批输出。
- 密钥只读环境变量 `DEEPSEEK_API_KEY`，不会写文件或打印。

## 本地运行

依赖 Python 3.11+：

```bash
cd hermes/arsenal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

真实采集：

```bash
python3 collect.py
```

没有 DeepSeek key 时，用固定 8 条样例验证全链路。样例明确标为 `by: "一一(dry-run)"`，不是当天真实推荐；校验仍兼容旧的 `Hermes(dry-run)`：

```bash
tmp_dir="$(mktemp -d)"
python3 collect.py --output "$tmp_dir/candidates.jsonl"
python3 distill.py --dry-run \
  --candidates "$tmp_dir/candidates.jsonl" \
  --output "$tmp_dir/arsenal.json"
python3 distill.py --validate-only "$tmp_dir/arsenal.json" \
  --candidates "$tmp_dir/candidates.jsonl"
```

有 key 时：

```bash
export DEEPSEEK_API_KEY='在本机输入，不要发到聊天或写进仓库'
./run.sh
```

可指定上海日期；`--dry-run` 会完成采集后用固定样例蒸馏：

```bash
./run.sh 2026-08-23 --dry-run
```

## 服务器安装到 `/opt/hermes-arsenal/`

```bash
sudo install -d -m 0755 /opt/hermes-arsenal
sudo rsync -a hermes/arsenal/ /opt/hermes-arsenal/
sudo python3 -m venv /opt/hermes-arsenal/.venv
sudo /opt/hermes-arsenal/.venv/bin/pip install -r /opt/hermes-arsenal/requirements.txt
sudo chmod +x /opt/hermes-arsenal/run.sh
```

运行时显式告诉蒸馏器站点仓库位置，并从既有 Hermes env 文件加载 key：

```bash
set -a
source /data/second-brain/hermes/.env
set +a
export XF_REPO=/opt/xfsite/repo
/opt/hermes-arsenal/.venv/bin/python /opt/hermes-arsenal/collect.py
```

## cron：每天 23:45 CST

用 `crontab -e` 添加；`CRON_TZ` 避免宿主机使用 UTC 时错跑：

```cron
CRON_TZ=Asia/Shanghai
45 23 * * * /bin/bash -lc 'set -a; source /data/second-brain/hermes/.env; set +a; export XF_REPO=/opt/xfsite/repo; export PATH=/opt/hermes-arsenal/.venv/bin:/usr/local/bin:/usr/bin:/bin; /opt/hermes-arsenal/run.sh' >> /var/log/hermes-arsenal.log 2>&1
```

注意：cron 只负责知识采集与蒸馏。`scripts/daily-publish.sh` 随后的静态构建会读取当日 `site/content/arsenal/YYYY-MM-DD.json`；前端必须存在对应 content reader/page，文件才会真正进入 `site/out/`。

## 自检

```bash
python3 -m compileall -q .
PYTHONPATH=. python3 -m unittest -v test_arsenal.py
bash -n run.sh
```

退出码：参数/缺 key/候选不足为 `2`；采集或蒸馏失败为 `1`。任何失败都不会用半文件覆盖上一份有效 JSON。
