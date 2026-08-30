#!/usr/bin/env bash
# 早上 07:00（北京）开工：出刊日期 = 昨天，素材覆盖昨天 00:00–24:00 全天（含深夜）。
set -euo pipefail
printf '本期出刊日期：%s（Asia/Shanghai，即昨天一整天）；今天是 %s，仅作参考，不要蒸今天。\n' \
  "$(TZ=Asia/Shanghai date -d yesterday +%F)" "$(TZ=Asia/Shanghai date +%F)"
