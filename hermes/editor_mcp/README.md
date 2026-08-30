# ai325_editor MCP

给 Hermes Agent 的「一一总编」stdio MCP。它只编排仓库现有脚本，不复制蒸馏、评分或发布算法。

## 工具

| 工具 | 行为 | 是否发布 |
|---|---|---|
| `run_ledger(date)` | 调 Ledger 蒸馏器与 judge，返回分数、hard/soft、建议和路径 | 否 |
| `run_arsenal(date)` | 采集、蒸馏到 quality staging 并 judge；失败后的第二次调用自动带上一轮建议重蒸一次 | 否 |
| `redistill_theme(date, idx, feedback)` | 只把候选成品的 `themes[idx]` 合回原日报，校验失败自动恢复，再 judge | 否 |
| `publish(date)` | 双 judge 与 `complete=true` 预检后调用 `server-daily.sh --publish-only`；输入指纹相同则直接返回。MCP annotation 明确标为 destructive/open-world 生产写操作 | 是 |
| `status(date)` | 汇总 artifact、judge、quality、ALERT 和发布标记 | 否 |
| `alert(text)` | 覆盖写 ALERT、追加 export.log，并调用 `scripts/ops/alert.sh` 进入统一邮件/outbox | 否 |

所有写工具与 `scripts/server-daily.sh` 共用 `${AI325_EDITOR_LOCK_FILE:-/opt/xfsite/logs/ai325-editor.lock}`。MCP 持锁调用发布脚本时传 `AI325_EDITOR_LOCK_HELD=1`，避免自身二次加锁。23:55 fallback 最多等锁 1800 秒；若当日 Agent 已成功发布则退出，否则跑原纯脚本全流程。

## 本地验证

服务端使用独立 venv。Hermes 当前客户端可能安装 MCP 2.x，但 FastMCP server 模块来自官方 Python SDK 1.x，因此 requirements 显式约束 `<2`，不会改变 Hermes Agent 自身 venv。

```bash
python3 -m py_compile hermes/editor_mcp/server.py
uv run --with 'mcp[cli]>=1.12,<2' \
  python -m unittest -v hermes/editor_mcp/test_server.py
uv run --with 'mcp[cli]>=1.12,<2' \
  python hermes/editor_mcp/server.py --list-tools
```

正式 stdio 握手还应通过 MCP Inspector 或 Hermes 客户端执行，不能只以进程可启动代替。

## 服务器部署

先只读检查：

```bash
cd /opt/xfsite/repo
bash hermes/editor_mcp/deploy.sh --plan
hermes --version
hermes mcp list
hermes cron list --all
hermes tools list --platform wecom
hermes send --list wecom
```

确认路径后执行：

```bash
sudo -E bash hermes/editor_mcp/deploy.sh --apply
```

脚本在任何 Hermes 配置写入之前建立：

- `$HERMES_HOME/config.yaml.pre-ai325-<timestamp>`；
- `$HERMES_HOME/cron/jobs.json.pre-ai325-<timestamp>`（若原文件存在）；
- `/etc/cron.d/ai325-editor-fallback.pre-ai325-<timestamp>`（若原文件存在）；
- `/opt/ai325-editor.pre-ai325-<timestamp>`（若原目录存在）。

MCP 使用 `hermes mcp add ai325_editor ...` 只新增/更新 `mcp_servers.ai325_editor`，不会替换整个 `mcp_servers`，因此既有 `second_brain_kb` 保留。部署脚本不会运行 `hermes tools enable`，避免在隐式平台配置上连带实体化 terminal/file/code_execution。若 WeCom 已显式列出某些 MCP server 形成 allowlist，脚本只向原数组末尾追加 `ai325_editor`；若存在 `no_mcp` 则尊重安全选择并停止，不自动覆盖。

既有 `ai325-editor-daily` 会从已备份的 `jobs.json` 精确找到唯一 job id，再用 `hermes cron edit` 更新 prompt、schedule、delivery、script 与 workdir 并 resume；不会因“同名已存在”静默沿用旧 prompt。fallback cron 文件带 `# managed-by: ai325_editor`，若目标路径已有不带标记的文件，部署会在任何配置写入前停止而非覆盖。

部署脚本不会自动发送外部消息。应用后由操作者单独执行以下连通性测试：

```bash
hermes mcp test ai325_editor
hermes send --to wecom '[一一总编] 主动复命连通性测试'
```

若 WeCom 主动发送失败，不应阻塞内容生产；失败流程仍写 `/opt/xfsite/logs/ALERT`、`/opt/wechat-archive/export.log`，调用统一邮件/outbox，并刷新 `site/public/health/daily.json`。

## 回滚

使用部署输出中同一 timestamp 的明确文件，不要用通配符猜最新备份：

```bash
sudo cp -p /data/second-brain/hermes/config.yaml.pre-ai325-<timestamp> \
  /data/second-brain/hermes/config.yaml
sudo cp -p /data/second-brain/hermes/cron/jobs.json.pre-ai325-<timestamp> \
  /data/second-brain/hermes/cron/jobs.json
# 仅当部署前 cron 文件存在时恢复：
sudo cp -p /etc/cron.d/ai325-editor-fallback.pre-ai325-<timestamp> \
  /etc/cron.d/ai325-editor-fallback
sudo systemctl restart hermes-gateway.service
```

如果部署前没有 fallback cron 文件，确认目标确为本次新增后再移走 `/etc/cron.d/ai325-editor-fallback`；不要做宽泛删除。
