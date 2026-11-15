# 抓取许可判定的现有边界

这是爬虫已选好用户代理规则组后的内部匹配器，不下载或解析 robots.txt。
policy.Policy(rules).allowed(url) 返回 bool。实例创建后规则集固定，查询不修改规则。
rules 是 list 或 tuple，每项是二元素 list/tuple：[action, pattern]。
action 仅为小写 allow 或 disallow；pattern 是字符串。
空模式忽略，其他模式必须以 / 开始；重复规则合法。
调用方不必保留或修改传入容器，实例不得因调用方随后修改容器而改变判定。

## 路径与匹配

normalization.py 是既有规范化实现，须直接复用并保持文件不变。
url 必须是含主机的绝对 http/https URL。整个输入的字符和转义先接受校验。
匹配对象为路径及存在时的 ?query，空路径视为 /，片段不参与匹配；空查询仍保留 ?。
规范化将百分号十六进制统一为大写，只解码未保留 ASCII 字节，
其他转义保留为三字节 %XX；原始非 ASCII 字符按 UTF-8 转为 %XX。
ASCII 空格、ASCII 控制字符、非法百分号转义、非法 Unicode、无效端口等沿 helper 抛 ValueError。
这不是新增完整 URL/robots 协议实现任务，以 helper 的实际行为为兼容边界。

模式中原始 * 表示任意长度（含零）的规范化字节串，连续 * 合法。
仅最后一个原始 $ 是结束锚，其他位置的 $ 为普通字节。
先识别通配符与末尾锚，再分别规范化文字部分；%2A 和 %24 不是元字符。
所有模式从路径起点匹配；无末尾锚时命中前缀即可。
优先级分数是 rule_parts 返回的 score，即规范化后所有文字部分的字节长度之和，
不计算 * 及结束锚。%2F 的分数贡献为 3，不等同于 /。
最高分命中规则决定结果，同分 allow 胜出，没有命中则允许。
非法规则在构造时抛 ValueError，非法 URL 在查询时抛 ValueError；
失败查询不能影响下一次合法查询。

例如 rules=[["disallow","/private/*"],["allow","/private/open$"]]：
https://p.example/private/open 得 true；
https://p.example/private/open/x 得 false。
samples.py 另有 Unicode、百分号转义、查询串与片段样例。
checks.py 除业务回归外包含独立的小规模动态规划判定器，不用参照的正则实现。

## 本轮允许修改的部分

替换 policy.py 的正确逐规则实现，可新增内部实现模块和核验材料。
reference.py、normalization.py、samples.py、checks.py、bench.py 和 verify.py 保持原样。
新增的差分和边界核验接入独立脚本即可，不删除、弱化或绕过原断言。
不得针对固定负载、规则表规模或 URL 预置判定结果。
索引仅由当前实例规则集构建一次；本实例的全部准备工作须计入构建。
不跨实例缓存索引，不将构建延迟到计量外。查询须复用规则间共享的匹配状态；
不允许逐规则正则/函数扫描，也不允许简单拼接逐规则备选分支成一个大正则。
不要求规则在线增删、网络访问、持久化或抓取调度。

## 公开核验与性能口径

python3 checks.py verify 核对既有兼容性；python3 checks.py demo 展示六项真实判定。
python3 bench.py baseline 输出基线计量且核对结果相同，不强制优化阈值。
python3 bench.py target 使用同一固定负载并启用优化断言。
两组负载分别是 4096 条共享长前缀规则及 4098 条交叠通配规则，各查询 192 个 URL。
每轮重新构造实例，参照和目标交替先后执行；共三轮。
每组查询耗时中位数须不超过同进程参照的 1/5。
每组构建耗时中位数须不超过 3 秒。
每组构建中位耗时加三倍查询中位耗时须不超过参照同式结果。
各组从构建到查询完成的 Python 分配峰值须不超过 48MiB，不含预先生成的输入。
计时与内存分开测量，峰值用 tracemalloc；baseline 模式不代表已达优化目标。
BASELINE.md 提供原始实测记录，绝对耗时仅作背景，验收重跑同进程对照。
交付实测值和简短状态说明，解释通配符可取零长度、重叠匹配及优先级如何保真。

## 运行清单

.pointwise-runtime.json 的 version 为 1、kind 为 cli；setup 为准备命令 argv 数组的列表，
verify、demo 分别为核验和真实演示的单条 argv 数组。本项目 setup 为空。
现有 verify 为 ["python3","verify.py","baseline"]，同时跑业务回归和基线计量。
优化完成后，将 verify 改为 ["python3","verify.py","target"]。
demo 保持 ["python3","checks.py","demo"]，展示实际 URL 与 allowed 结果。
新增核验在交付说明中给出可重跑 argv，不以只打印成功替代业务核对。
