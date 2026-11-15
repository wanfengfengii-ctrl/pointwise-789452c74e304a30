# 优化交付说明与可重跑实测

## 改了什么

policy.py 由"每条规则一个正则、逐条尝试"替换为单次建索引、单次扫描的共享自动机，
接口不变（policy.Policy(rules).allowed(url) -> bool），normalization.py 直接复用，
reference.py、normalization.py、samples.py、checks.py、bench.py、verify.py 未动。

## 状态如何维护（构建一次，查询共享）

构建（仅 __init__，全部计入构建耗时，不跨实例缓存）：
1. 规则经 rule_parts 解析校验后，空字面值段剔除（`*` 之间的空段是 no-op，
   `.*.*` 等价于 `.*`）；末尾为空段的锚定规则退化为非锚定（尾部 `.*` 已能到达路径末尾）。
   全部为空段的规则（如 `/**`）以分数 0 匹配一切路径，合并为一个 allow 取或的标志。
2. 所有去重非空字面值装进一棵 Aho-Corasick 自动机（字节 trie + fail 链，
   输出按 fail 链预合并），另建一棵"规则 trie"：根到节点的路径是规则的字面值序列，
   跨规则共享前缀；节点保存终结信息（score 由路径推出，同分 allow 取或，
   锚定/非锚定各一格），以及"最早结束位置"槽位。

查询（allowed）：
- url_path 规范化（校验失败抛 ValueError，且发生在任何内部状态被触碰之前，
  失败查询不影响后续查询）；随后查询代数 +1。
- 路径只做一次从左到右的 AC 扫描，逐位置得到所有字面值出现（含重叠，
  经 fail 链合并输出）。每个出现沿"规则 trie 的边表"推进共享状态：
  首字面值必须起始于偏移 0；其余只要求父节点最早结束位置 ≤ 本次起点，
  故 `*` 可取零长度（允许紧邻），重叠出现由 AC 全部报告、由位置约束自然取舍。
  出现按结束位置递增到达，节点首次被打上本代戳即是最早结束，无需每查询清零数组，
  查询代价只正比于真实出现数，绝不逐规则扫描，也没有拼接大正则。
- 非锚定终结在节点首次到达时计入候选；锚定终结要求该次出现恰好结束于路径末尾
  （对每个出现单独检查）。优先级分数即规范化后字面值字节总长（%2F 计 3），
  候选按 (score, allow) 取最大，同分 allow 胜，无命中允许——与参照逐点对拍一致。

## 核验方式（可重跑）

- `python3 checks.py verify`：既有业务回归（6 例 + 2100 组随机对拍）。
- `python3 diffcheck.py`：新增独立差分与边界核验。边界 100+ 例（空规则、空模式、
  `*`/`$` 各位置、`%2A`/`%24`/`%2F` 字面语义、Unicode、查询串与片段、同分 allow 优先、
  重复规则、锚定退化、通配零长与重叠），260 组随机规则×24 URL 三方对拍
  （优化版 vs 参照 vs 独立动态规划判定器），外加结构化共享前缀/交叠通配负载、
  非法规则/URL 的 ValueError 行为、失败查询隔离、调用方改容器不影响判定、实例间隔离。
- `python3 bench.py target` 或 `python3 verify.py target`：固定负载 + 优化断言。
- `python3 checks.py demo`：六项真实判定。

## 实测（Python 3.11.2，x86_64 容器，2026-11-15，本目录直接运行）

`python3 checks.py verify` →
{"business_cases": 6, "random_comparisons": 2100, "result": "compatible"}

`python3 diffcheck.py` → {"comparisons": 6572, "result": "differential-ok"}

`python3 verify.py target`（三轮中位数，秒；峰值字节）：
shared_prefix（4096 规则 / 192 查询）：
  reference_build_s=0.301114，target_build_s=0.075712（≤3 秒）
  reference_query_s=0.143840，target_query_s=0.007420，query_ratio=0.0516（≤1/5）
  target_peak_bytes=11444212（≤48MiB）
  build+3×query：reference=0.732633，target=0.097972（不超过参照）
wildcard_overlap（4098 规则 / 192 查询）：
  reference_build_s=0.119869，target_build_s=0.022458（≤3 秒）
  reference_query_s=0.144793，target_query_s=0.003194，query_ratio=0.0221（≤1/5）
  target_peak_bytes=2969579（≤48MiB）
  build+3×query：reference=0.554247，target=0.032040（不超过参照）

`python3 checks.py demo` 六项判定依次为 true、false、false、true、false、true，
与 BASELINE.md 记录一致。

绝对耗时仅作背景，验收以同进程参照对照为准；核验配置已按契约切换为
["python3","verify.py","target"]（.pointwise-runtime.json）。
