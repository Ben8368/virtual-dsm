# Production Integration Phase 4A: native ARM64 KVM validation

本文件保存 Phase 4A 验收协议和目标环境证据；当前阶段只在 [CONTEXT.md](../../CONTEXT.md) 维护。
既有 [Phase 3 F5](production-phase3.md#strict-f5-completed-acceptance-evidence--2026-10-15)
和 Watchdog L5 不提供原生 KVM 证据。磁盘仍为 DSM-compatible virtual layout。

## 2026-10-15 环境预检证据

采集窗口从 2026-10-15T07:55:26Z 开始。原始命令、stdout、stderr 和返回码保存在
忽略目录 research/arm64/work/phase4a/ 的 preflight.json、commands.json 和各项 *.stdout.txt / *.stderr.txt；
这些是本机私有证据，不是 CI 工件或公开下载链接。

| 项目 | 实测结果 |
| --- | --- |
| 可用 Linux 环境 | WSL2 Ubuntu 24.04.4 LTS；uname -m=x86_64 |
| CPU | Intel Core i7-10700 @ 2.90 GHz；16 logical CPUs；VT-x；Microsoft hypervisor |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 |
| /dev/kvm | 字符设备 10:232，root:kvm，0660；WSL 当前用户不在 kvm 组，不具备读写权限 |
| Docker | Engine/Client 29.9.0，linux/amd64；containerd 2.4.1；runc 1.5.2 |
| 远端入口 | Docker 只有本机 default context / builder；Windows 与 WSL 用户均无 SSH config；本轮未提供 ARM64 连接目标 |
| 既有生产镜像 | virtual-dsm:phase3-http-0004；linux/amd64；image ID 0d1c3b9b4b217fae738bb78a0bdadc65155f1c3c4afcc23f780abc4eb011b263 |
| AArch64 QEMU | /usr/local/bin/qemu-system-aarch64，8.2.2 (v8.2.2-dirty) |
| QEMU SHA256 | a6d76b56ec166c8df897387cbc708fffbfd9d1600dc9a0700cb7226671ecbfda；与严格 F5 记录一致 |
| -accel help | 仅 tcg；-machine help 含 virt；-cpu help 已保存 |
| 显式 KVM 阴性对照 | -machine virt,gic-version=3 -accel kvm -cpu host 初始化退出 1：invalid accelerator kvm |
| ARM CPU / LPA2 | 未采集：没有 ARM64 目标；不能从 Intel flags 推断 ARM ID-register 或 KVM 暴露 |

阴性对照通过 Docker --device /dev/kvm 在独立、只读、无网络容器中运行；没有挂载 DSM 磁盘，
没有 TCG 回退。它证明本机这份 amd64 AArch64 QEMU 不支持 KVM，不代表任何原生 ARM64 主机失败。
主机采集的返回码 1 对应最后的 /dev/kvm 读写检查失败；前面的 uname、os-release、nproc、lscpu、ls 和 stat 已保存。
本轮不修改设备权限，也不启动、关停或复制既有 Phase 3 访客。

## 生产加速器策略审查

唯一平台契约见 [platforms.md](../../docs/platforms.md#cpu-and-hardware-policy)，
实现为 src/platform/rtd1619b.sh 的 platformDefaults、platformConfigureCpu 和 platformKvmProbe。

- amd64：TCG multi，CPU max,lpa2=off。
- ARM64：KVM 请求开启、/dev/kvm 可读写且实际 QEMU virt/GICv3 + host CPU 初始化成功，才选择 KVM。
- 无权限或初始化失败：当前继续使用 TCG；选择分支自身没有明确的降级警告。
- 建议保留已接受的 TCG 回退契约，并在后续源码变更中加入可操作的降级警告和确定性分支测试。
  本轮仅评审、记录建议；不改变生产行为。该策略不保证 host CPU 与 stock DSM 内核兼容。

QEMU 8.2.2 的本地源代码 target/arm/cpu64.c 中 arm_cpu_lpa2_finalize 明确注明
lpa2 property 只安装于 TCG -cpu max。因此不能把 TCG 的 lpa2=off 直接当作 KVM host 的可用属性。
这不是实际 ARM 主机的 QOM 属性枚举结果；需要在目标构建中验证，不编造 host,lpa2=off。

## 真机交接：先完成独立 KVM 和 CPU 特征检查

使用真实 AArch64 Linux 主机；保持生产 QEMU 8.2.2、0001–0004 和既有硬件模型。
先记录以下原始输出和每条命令返回码，再访问任何 DSM 磁盘：

~~~bash
uname -a
uname -m
cat /etc/os-release
nproc
lscpu
cat /proc/cpuinfo
ls -l /dev/kvm
stat /dev/kvm
id
test -r /dev/kvm && test -w /dev/kvm
docker version
docker info
qemu-system-aarch64 --version
qemu-system-aarch64 -accel help
qemu-system-aarch64 -machine help
qemu-system-aarch64 -cpu help
printf 'quit\n' | timeout 10 qemu-system-aarch64 \
  -machine virt,gic-version=3 -accel kvm -cpu host \
  -smp 1 -m 128 -nodefaults -display none -serial none -monitor stdio -S
~~~

最后一个无盘探针必须返回 0。容器内再对生产二进制执行同样检查；主机检查成功不能代替容器权限。
确认 uname -m=aarch64/arm64、没有跨架构 binfmt 执行；没有真正 ARM64 主机时停在 K0。

CPU 记录必须包含 implementer、part、revision、虚拟化扩展、主机页大小和支持的 granule、PA/IPA 限制。
需要时使用仅在忽略目录编译的小型研究 helper；保存源码与原始读数，不提交二进制。
记录 MIDR_EL1、ID_AA64PFR0_EL1、ID_AA64MMFR0_EL1 等实际可读寄存器及采集上下文，
特别区分 host EL0 的受内核过滤读数与 KVM vCPU 的 guest-visible ID-register 状态。
对 LPA2 要保存 TGran4、TGran16、stage-2 granule 字段及解释依据；单独的 lpa flag 或 PA 位数不够。
无法读取的字段写 unknown，不能写 LPA2=off。

首个受控生产启动使用 -accel kvm -cpu host，完整捕获 early serial。
遇到 __no_granule_support 或等价 CPU-feature 故障，立即停止该尝试并分类；不改 DSM kernel。
只有确实发生此类故障后才研究目标 QEMU/KVM 的实际 CPU properties 与安全掩码支持。
若没有受支持的正常配置路径，先记录 host compatibility constraint；不全局改写 KVM ID registers。

## 配置态磁盘和生产启动门禁

1. 以严格 F5 清理后的配置态资产为来源，先确定它已停止、没有写入者；禁止复制正在使用的可变 raw 镜像。
   保护源和账号准备快照保持只读；准备一个独立、可丢弃的完整 generation 副本，包含 kernel/initrd、manifest 和指针。
   记录来源身份、传输前后 SHA256、镜像 digest、补丁序列、配置态磁盘一致性和 provenance。
   不跨架构比较可执行文件 SHA256；原生 ARM64 二进制需要独立构建与身份记录。
2. 启动前在停止的副本上只读确认 configured=true、sata1p3 / volume1、PostgreSQL 数据及 marker；
   运行后再交叉核对实际服务和挂载，不能把 manifest 当作健康证据。
   marker 必须为 /volume1/phase3-persistence.txt，SHA256
   85c85894c2c5e1168f2c046c3d23dbc9dddd57fd8d6ef0e8c7f37c49d62b7e31。
3. 使用正常 /usr/bin/tini -s /run/entry.sh；KVM=Y、DSM_PLATFORM=rtd1619b、2 vCPU，
   保持 USB CDC ECM + user hostfwd 与既有存储。容器显式映射 /dev/kvm，设置自身端口，不替换现有访客。
   现有 compose.local.yml 的 KVM=N 不可直接当 KVM 验收配置。
4. 保存正常启动日志与 /proc/<qemu-pid>/cmdline 的 NUL 分隔原始 argv，确认
   HOST_ARCH=arm64、GUEST_ARCH=arm64、QEMU_BIN=qemu-system-aarch64，
   最终 -accel kvm、-cpu host，没有任何 TCG 选项；QMP query-kvm 同时要求 present=true、enabled=true。
   验收流程发现生产回退必须拒收该次 KVM 运行，不能把正常 TCG 就绪计入 KVM。
5. 0004 保留在生产构建中。保存四补丁应用/构建证明和二进制身份；源码改动仅在 accel/tcg 和 target/arm/tcg。
   实际 KVM 运行后才能填写“0004 active in binary: yes；0004 runtime path used under KVM: no”。
   组合最终 argv、query-kvm 及执行路径证据；若需动态探针，在调试副本观测 helper 入口，
   保留探针附着成功和采样边界，不能仅以空日志宣称未执行。本轮这两项尚无 KVM 运行证明。

## 真机验收与分类门禁

| Gate | 必需证据 |
| --- | --- |
| K1 | 独立 KVM 初始化成功、生产 KVM 已启动，但 DSM 未启动完成；保存最早失败串口与 feature 分类 |
| K2 | KVM 下 DSM systemd/login；ttyS0 console、ttyS1 control UART、AHCI/sata1、LED/syscon/scemd、XHCI/CDC ECM/eth0 全部核查 |
| K3 | configured=true；sata1p1 root、sata1p3、Btrfs /volume1 健康；PostgreSQL/scemd 活跃；nginx/web ready；DHCP/default route；HTTP/HTTPS 200；marker 一致 |
| K4 | 同一配置态副本共 3 次冷启动（至少 2 次 restart）；首次至少 30 guest minutes，30/30 HTTP GET 200、HTTPS 200；每次复核 K3；至少两次 DSM UI 干净关机 |
| K5 | K4 已通过后，独立空存储 + 官方 DSM_DS124_72806.pat 经原生产自动安装、provenance 和持久化验收 |

每次冷启动记录 boot-to-login、boot-to-HTTP、boot-to-full-readiness、host CPU、guest uptime、
完整 serial/journal/dmesg/messages 与服务快照。完整日志扫描 soft/hard lockup、RCU stall、Oops、BUG、
panic、NULL pointer、SError、alignment fault、driver probe failure；记录全部命中并人工区分真实故障和文本假阳性。
不可只扫描最后几行；不改变 watchdog，也不伪造 configured/volume/HTTP 状态。

每次接受的关机要求 DSM UI 触发、systemd shutdown、All filesystems unmounted、reboot: Power down、
QMP guest=true/reason=guest-shutdown、QEMU rc=0，且无 host SIGTERM/SIGKILL 回退；核查 ttyS1 没有 fault。
每次启动与关机后复核 marker；不重建、替换或缩小配置态系统盘。

K5 的空盘实验另建存储，复用完全相同的官方 PAT validation/provenance：
PAT -> artifacts -> system.img -> boot -> web installer/login -> 正常配置；若执行建卷则记录路径，
随后 restart 验证配置与数据。若未执行建卷则明确边界，不由空盘登录页面推断持久服务健康。

## 主机兼容记录与性能比较

| 字段 | 本轮结果 |
| --- | --- |
| ARM SoC / CPU、kernel、KVM、QEMU | 无目标；现有环境身份见预检表 |
| 最终 KVM CPU policy、LPA2 guest exposure、DSM result | 未运行 / unknown |
| 已证明的兼容范围 | 仅本机不具备 AArch64 KVM 验收条件；不推断任何 ARM64 主机兼容性 |
| 第二主机 | 未提供；可用后按不同 CPU generation 做 smoke，不是单主机验收的硬门禁 |

| Metric | 严格 Phase 3 TCG，3 boots | Native ARM64 KVM |
| --- | --- | --- |
| boot-to-HTTP | 401.247 / 407.629 / 391.015 s | 未测 |
| full-readiness | 562.833 / 537.703 / 533.529 s | 未测 |
| host CPU usage | 本轮未汇总同口径数据 | 未测 |
| guest watchdog events | 既有严格 F5 无 soft lockup / RCU stall / Oops / panic | 未测 |
| HTTP responsiveness | 既有 30/30 HTTP 200、HTTPS 200；未汇总延迟分布 | 未测 |
| shutdown duration | 两次 guest-shutdown 已通过；本轮未计算同口径耗时 | 未测 |

时间来自忽略证据 phase3-f5/strict-f5-final.json 的 boot_readiness，
不是本轮新增启动结果。KVM 应按同样采样边界记录至少三次；不能从一次运行宣称性能提升。

## 本轮验证

2026-10-15 本轮检查全部返回 0；详细 stdout/stderr 和返回码保存在忽略证据目录 tests.json。
源码与生产行为未变，因此未新增 accelerator-selection 测试；已有 amd64 -> TCG snapshot 随 smoke 执行。
真机 CPU feature、KVM 访客生命周期与安装验收未运行。

| 命令 | 结果 |
| --- | --- |
| shellcheck -x src/*.sh src/platform/*.sh research/arm64/*.sh research/arm64/tests/*.sh | PASS，rc=0 |
| bash research/arm64/tests/smoke.sh | PASS，rc=0；含现有 platform 测试 |
| bash tests/qemu-patches.sh research/arm64/work/qemu-src | PASS，rc=0；使用本地 exact upstream v8.2.2 Git 源，四补丁全部 clean apply |
| git diff --check | PASS，rc=0 |
| python -X utf8 scripts/governance-docs-check.py | PASS，rc=0；Windows Python 3.14，等价执行既有 python3 脚本 |

补丁测试传入脚本已有的本地源参数，避免重复下载；未修改测试或生产源。
治理检查在 Windows 原生 Python 执行；WSL 下同一脚本的目录遍历耗时较长，未取得该次结果。
Git 的 LF -> CRLF 配置提示不属于 diff whitespace 错误；本轮四份文档实际均为 UTF-8 LF。
