# Hermes Ledger Distiller

把 `/opt/hermes-ledger/materials/YYYY-MM-DD/` 中的群聊全文蒸馏为同目录的 `content.json`。输出遵循 `_hermes_spec.md` 的八段结构、三档语气、深潜写法、原文纪律和网站扩展字段。

## 处理链路

```text
transcript.txt + stats.json + context-prev.md + newcomers.json?
  → 全文按行切片（默认 5,500 字符/片，所有行只进入一个片段）
  → DeepSeek 逐片抽取最多 25 条证据（单片 JSON 控制在 6,000 字符内）
  → 携上一期 threads / docket / glossary 生成紧凑八段骨架
  → 第二轮按骨架填充最终 content.json
  → 本地软修剪 + 严格 schema + 自检
  → 原子替换 content.json
```

- `stats_override`、`members_total` 和 `hours` 始终回锁 `stats.json`；`speaker_count`/`members_total` 由数据库日窗口盖写，模型不能改写统计真值。
- transcript 每行先编号为 `L0001…`；模型只提交行号、署名及连续片段/字符偏移，程序再从原 transcript 回填 `quotes[].t` 与 `themes[].voices[].v`。比较时忽略空白并统一全半角标点与省略号，成品始终保留原始字符。
- 初次抽取不足 5 条逐字金句时，会从 stats 高频发言者的编号行补抽一次；仍不足才 hard fail。成功切片写入 `materials/.distill-cache`，后续切片失败重跑时不会重复调用已成功切片。
- 发送模型前会打码手机号，并移除疑似密码、口令、密钥和长令牌所在消息；任何密码类内容都不会进入成品。
- 一般列表/字数超限、非法富文本、失真引文、无效日期、缺动词行动和可自动承接的 thread id 会修剪/丢弃单条并记 warning，不拒绝整份。
- 每幕 deep 的质量目标是至少 3 句、含一层以“没说破的：”开头、能定位时每个判断引一条原话，并以一天内动作收尾；只带 judge 原话局部补写，单幕最多 2 次，不重跑整份。补写后仍不足、缺引或错引只记 warning：错引会去掉引号改作普通判断，交由 judge 扣分，不拒绝整份。
- `themes[].voices[]` 独立携带 `g: s|j|h`。口径、治理产物、端点、静态、渲染、数据层、接线、缺口、闭环、赋能等工程腔会在 prompt 禁用，并由代码在非引文文本中替换。
- 模型漏掉 `title/lead/complete/coverage` 时，代码会用批次+首幕名、首幕 body 或 stats 句、`true`、任务日期+transcript 截止时间补齐。
- 最终硬闸门只包括：八段结构存在；`quotes/voices` 按行号回填后仍能按署名在 transcript 逐字定位；语气标记必须是 `s/j/h`；成品不得含手机号、身份证、密码/密钥或长令牌形态。其余句数、字数、deep 引文/动作和日期格式均自动修整或记 warning。
- 正式运行会为切片、骨架、填充、局部补写和最终校验打印阶段进度及阶段/累计耗时。默认总预算 1500 秒（可用 `--max-runtime` 调整）；超时停止后会优先落地内存中的最佳成品，或复用同路径已有候选，并以 `complete=false`、coverage note 的 `[partial]` 和运行摘要 `partial=true` 标记。
- 通用模型阶段失败会把上一版 JSON 和具体错误送回同一会话定点修复；主题幕局部补写独立限制为最多 2 次。非超时失败耗尽时旧 `content.json` 不会被半文件覆盖；进程超时则按上一条规则保存可用的 partial。
- 所有 DeepSeek 请求都使用 `response_format: {"type":"json_object"}` 和 `max_tokens: 8192`。JSON 若在数组对象中被截断，本地先丢弃最后一个不完整对象并闭合容器；修不好才重试。
- 重试提示会明确要求“只输出 JSON、不要多余字段、控制长度”，避免在同一 token 位置反复截断。

## 本地 dry-run

无需密钥。固定样例只从 `sample/transcript.txt` 选逐字材料：

```bash
python3 distill_ledger.py sample \
  --date 2026-08-23 \
  --dry-run \
  --output /tmp/hermes-ledger-content.json

python3 distill_ledger.py sample \
  --date 2026-08-23 \
  --validate-only /tmp/hermes-ledger-content.json
```

正式 `distilled_by` 为 `一一（Hermes × DeepSeek）`；dry-run 明确标成 `一一(dry-run)`，不能冒充真模型产物。校验仍兼容历史 Hermes 写法。

## 服务器安装与真跑

蒸馏器只用 Python 标准库，不需要额外 pip 依赖：

```bash
sudo install -d -m 0755 /opt/hermes-ledger
sudo rsync -a hermes/ledger/ /opt/hermes-ledger/
sudo chmod +x /opt/hermes-ledger/run.sh /opt/hermes-ledger/distill_ledger.py
```

`run.sh` 默认从 `/data/second-brain/hermes/.env` 加载 `DEEPSEEK_API_KEY`，不会打印密钥。材料根目录默认 `/opt/hermes-ledger/materials`，站点仓库用 `XF_REPO` 指定：

```bash
export XF_REPO=/opt/xfsite/repo
/opt/hermes-ledger/run.sh 2026-08-23
```

单独在每天 23:38 CST 蒸馏：

```cron
CRON_TZ=Asia/Shanghai
38 23 * * * /bin/bash -lc 'export XF_REPO=/opt/xfsite/repo; /opt/hermes-ledger/run.sh' >> /var/log/hermes-ledger-distill.log 2>&1
```

`scripts/server-daily.sh` 也有兜底：第 3 步转换前如果已有 transcript、尚无 content.json，就先调用本蒸馏器；失败只记 warning，站点继续沿用上一期日报。

## 自检

```bash
python3 -m compileall -q .
PYTHONPATH=. python3 -m unittest -v test_distill_ledger.py
bash -n run.sh
```
