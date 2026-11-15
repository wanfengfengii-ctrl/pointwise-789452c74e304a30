# 原实现的可重跑记录

业务入口：policy.Policy；policy.py 当前仅导出 reference.Policy，没有优化索引。
在 Python 3.9.6、arm64 上执行提供的源码，结果如下。
当前工作区只读，执行时用内存 import loader 加载这些完整文件；没有修改算法或负载。
交付后的普通目录运行命令及参数与 CONTRACT.md 一致，文件无需生成或安装依赖。

verify.py baseline 正常退出：
{"business_cases": 6, "random_comparisons": 2100, "result": "compatible"}

bench.py 的三轮中位数（秒），内存计量与计时分离：
shared_prefix：
reference_build_s=0.577432666，target_build_s=0.564208625
reference_query_s=0.356833708，target_query_s=0.349003125
query_ratio=0.978055372，target_peak_bytes=5235517
reference_build_plus_3_sweeps_s=1.647933790
target_build_plus_3_sweeps_s=1.611218000

wildcard_overlap：
reference_build_s=0.218600666，target_build_s=0.229524417
reference_query_s=0.275757792，target_query_s=0.291039292
query_ratio=1.055416385，target_peak_bytes=2190651
reference_build_plus_3_sweeps_s=1.045874042
target_build_plus_3_sweeps_s=1.102642293

target 与 reference 当前是同一实现；接近 1 的比例是正常基线波动。
baseline 模式不强制五倍提速；优化完成后运行 target 模式核验阈值。
checks.py demo 另已实际展示六项判定，依次为 true、false、false、true、false、true。
