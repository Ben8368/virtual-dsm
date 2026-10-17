# Production Integration Phase 4A: native ARM64 KVM validation

本文件保存 Phase 4A 验收协议和目标环境证据；当前阶段只在 [CONTEXT.md](../../CONTEXT.md) 维护。
既有 [Phase 3 F5](production-phase3.md#strict-f5-completed-acceptance-evidence--2026-10-15)
和 Watchdog L5 不提供原生 KVM 证据。Phase 4A 主路径是官方 PAT + 空 ARM storage 的新安装；Phase 3 F5 runtime 跨主机可移植性保持 UNTESTED，不是 K5 前置门禁。磁盘仍为 DSM-compatible virtual layout。

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

## 2026-10-15 Apple M5 nested ARM64 KVM preflight

Codex 控制主机为 macOS 26.6.2、MacBook Air Mac17,3、Apple M5（10 cores），自身没有 `/dev/kvm`。为验证硬件 KVM 路径，在独立 Colima 0.10.3 profile 中启动 ARM64 Ubuntu VM：VZ + nested virtualization；这不是 x86-to-ARM 仿真，但有 VZ 虚拟化层，不等同裸机 Linux。

| 项目 | 实测结果 |
| --- | --- |
| Linux host | Ubuntu 24.04.4 LTS；`aarch64`；kernel `6.8.0-117-generic`；4 vCPU、8 GiB |
| CPU | M5 物理主机；VM `/proc/cpuinfo` vendor Apple、implementer `0x61`、part `0x000`、revision `0`；VM MIDR 读数 `0x610f0000`；该虚拟 CPU 未给出可映射至 M5 核心型号的 part number |
| Virtualization / granule | `/dev/kvm` 字符设备 `10:232`，`root:kvm 0660`；VM user 最初无权限，加入此临时 VM 的 `kvm` 组后可访问；Linux `PAGE_SIZE=4096`，`CONFIG_ARM64_4K_PAGES=y` |
| Container runtime | Docker Engine/Client `29.5.2`，`linux/arm64`；containerd `2.2.4`；runc `1.3.5` |
| QEMU | Ubuntu QEMU `8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)`；`-accel help` 列出 `kvm`、`tcg`；`-machine help` 有 `virt`；`-cpu help` 有 `host`、`max` |
| KVM probe | `virt,gic-version=3 -accel kvm -cpu host -smp 1 -m 128 -nodefaults ... -S`；monitor `info kvm` 输出 `kvm support: enabled`；exit 0。探针无 TCG 参数、无回退 |
| KVM guest ID registers | 用上述 `-accel kvm -cpu host` 启动临时 bare-metal AArch64 ID-register probe：`MIDR_EL1=0x610f0000`、`ID_AA64MMFR0_EL1=0x000010000f100022`、`ID_AA64PFR0_EL1=0x1101000011110111` |
| LPA2 | KVM guest view：`TGran4=0`、`TGran4_2=0`；4 KiB translation 可用，FEAT_LPA2 对应的 4 KiB 值未暴露。QEMU 的 LPA2 编码为 `TGran4=1`、`TGran4_2=3`；16 KiB 的对应值为 `2` / `3`。因此此 nested guest 的 `-cpu host` 未暴露 LPA2。 |
| DSM result | 未启动：当前 checkout 不含严格 Phase 3 配置态 runtime disk（`research/arm64/work` 初始不存在）；遵守“先用配置态镜像”，未用空盘或重建系统盘代替 |

额外的 Linux userspace EL0 helper 读数为 `MIDR_EL1=0x610f0000`、`ID_AA64PFR0_EL1=0x0001000000110011`、`ID_AA64MMFR0_EL1=0x00000111ff000000`、`ID_AA64MMFR1_EL1=0x0000100000000000`、`ID_AA64MMFR2_EL1=0x0000000100000000`。其中 MMFR0 的 EL0/TGran4 读数与同一 VM 的 4 KiB kernel page size 矛盾，故不以这份 EL0 值推断 host LPA2；上表的 guest-visible 值来自实际 KVM vCPU probe。

该 VM 证明 Apple M5 上的 ARM64 Linux nested KVM 与 QEMU KVM 初始化可工作；它不代表 bare-metal ARM Linux，且没有严格 Phase 3 磁盘，所以未达到生产 KVM guest acceptance。阶段分类按严格原生 Linux host 与配置态 guest 门禁保持 K0；没有用 TCG 或 HVF 替代 KVM，也没有开始 Phase 22 空盘安装。

## 2026-10-15 ARM64 production image and KVM binary probe

本轮恢复并验证现有 `phase4a-kvm` Colima profile：Apple M5 / VZ，Ubuntu
24.04 ARM64，kernel `6.8.0-117-generic`，4 vCPU、8 GiB；`/dev/kvm`
在 VM 与容器内均可读写。Docker daemon 为 `linux/aarch64`、29.5.2。

在 ARM64 Docker daemon 上运行以下原生构建成功：

~~~bash
docker buildx build --no-cache --platform linux/arm64 --load -t virtual-dsm:phase4a-kvm .
~~~

Dockerfile 的 QEMU builder 确认上游 v8.2.2 commit
`11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea`，依次应用生产补丁 0001–0004，
并链接 `aarch64-softmmu`。最终镜像 `uname -m=aarch64`，二进制为
`/usr/local/bin/qemu-system-aarch64`，版本 `8.2.2 (v8.2.2-dirty)`，
SHA256 `55600fc63081177f61b9bf7251e360349fd89a97bc3944007712cd66b6659a20`。
二进制中可见 0004 的 `tb_invalidate_phys_page_dcz` 与
`tlb_invalidate_code_dcz` 符号。

最终生产二进制的无盘探针明确使用 `-accel kvm -cpu host`，QEMU monitor
`info kvm` 报告 `kvm support: enabled`，没有 TCG 参数或回退。该探针只
验证生产 QEMU/KVM 初始化，不执行 DSM，也未执行 0004 的 TCG helper。

本轮 checkout 的 `research/arm64/work` 不含 Phase 3 runtime，且当前执行环境
没有 WSL 源机的 SSH/rsync 目标；故无法证明源盘已停止、验证代次或传输。
没有启动 DSM、没有清洁安装。分类仍为 K0：ARM64 KVM 预检通过；DSM runtime
尚不可用，因此 DSM boot 未尝试。此证据属于 Apple M5/macOS/Apple VZ 上的
ARM64 Ubuntu nested Linux KVM，不证明 bare-metal Linux ARM64 或其他 Apple CPU。

## 2026-10-15 fresh-install continuation gate

按本轮 Phase 4A 新目标，旧 Phase 3 runtime 的恢复与跨主机复制不是前置步骤；其跨主机可移植性保持 `UNTESTED`。精确文件名 `DSM_DS124_72806.pat` 在项目 ARM64 忽略工作区、Downloads、Desktop、`/Volumes`、Spotlight 索引及排除缓存目录后的用户目录查找中均未发现，故未计算或假设 PAT hash，也未尝试下载/安装。官方 PAT 门禁结果：`OFFICIAL PAT REQUIRED`。

本机再次确认 macOS 26.6.2、MacBook Air Mac17,3 / Apple M5；现有 Colima `phase4a-kvm` profile 为 `Broken`，`colima status` 报未运行，`limactl list` 无实例，Docker daemon socket 拒绝连接，macOS 没有 `/dev/kvm`。普通 sandbox 启动因无法写入用户配置目录失败；授权范围内重试返回“already running”，但后续状态核验仍显示无实例。为避免在官方 PAT 门禁关闭时重建虚拟机，未重建 profile、未运行 Stage 2 容器探针。没有 DSM boot；分类维持 K0。既有 M5/Colima/KVM/生产镜像记录仅代表先前采集时的证据，不代表本次 Colima 状态可用。

## 2026-10-15 Colima environment recovery

本轮使用宿主权限重新检查后确认，`phase4a-kvm` 并未损坏或丢失：普通沙箱内的 Colima/Lima 查询被禁止读取 macOS boot-session ID，因而误报 `Broken` / 无实例；宿主权限下 `colima status` 与 `colima list` 均报告 profile 正在 VZ 中运行。没有删除或重建 profile。配置为 ARM64、VZ、4 vCPU、8 GiB RAM、100 GiB Docker disk、nested virtualization=true。用户 `ben` 属于 `kvm` 组；Linux guest 为 Ubuntu 24.04.4、`aarch64`、kernel `6.8.0-117-generic`，`/dev/kvm` 为 `root:kvm 0660`，读写通过。macOS 26.6.2，MacBook Air Mac17,3 / Apple M5。

Docker Client 29.9.0、Engine 29.5.2，daemon `linux/arm64`。容器清单与数据卷均为空，`research/arm64/work` 不存在；没有发现 Phase 3/4 DSM runtime。保留原 100 GiB data disk，其中仍有现存生产镜像和 Docker 构建缓存。镜像 `virtual-dsm:phase4a-kvm`，image ID `sha256:1a37d61213916de79b36fb551ce3531a1fccedd2b51bda82009f5b9e9a340973`，架构 `linux/arm64`；`/usr/local/bin/qemu-system-aarch64` 为 QEMU `8.2.2 (v8.2.2-dirty)`，SHA256 `55600fc63081177f61b9bf7251e360349fd89a97bc3944007712cd66b6659a20`。0001–0004 仍为该生产构建系列；0004 的 `tb_invalidate_phys_page_dcz` 与 `tlb_invalidate_code_dcz` 符号存在。

从该镜像启动仅运行 shell 的容器，使用 `--device /dev/kvm`；容器内 `uname -m=aarch64` 且 `/dev/kvm` 可读写。生产 QEMU 无盘探针显式使用 `-machine virt,gic-version=3 -accel kvm -cpu host`，monitor 报告 `kvm support: enabled`，进程正常退出；argv 未提供 TCG accelerator，也无回退。此为环境探针，不构成 DSM boot 证据，Phase 4A 仍为 K0。指定 PAT 仍不存在本机，故停止于 `OFFICIAL PAT REQUIRED`；未下载 PAT、未启动 DSM、未运行安装流程。

## 2026-10-15 official-PAT fresh KVM boot

根据用户指明的 Synology CDN URL 下载官方 `DSM_DS124_72806.pat`：
`https://global.synologydownload.com/download/DSM/release/7.2.2/72806/DSM_DS124_72806.pat`。
文件大小 319,317,444 bytes，SHA256
`17f48a9a4572c9b3b994921d3fb410d8186e9c4bf02cf9334e37897e5752e1dd`，与门禁完全一致；本地副本位于忽略目录 `research/arm64/work/phase4a/pat/DSM_DS124_72806.pat`，mode 0600。Docker 只读挂载再次得到相同 SHA。中间下载分段和 PAT 均留在忽略目录，没有加入 Git。

新建 Docker 卷 `phase4a-kvm-fresh-20261015`，安装前在生产镜像容器中确认 `/storage` 空目录。生产镜像 `virtual-dsm:phase4a-kvm` 的默认 entrypoint `/usr/bin/tini -s /run/entry.sh` 直接运行，挂载 `/dev/kvm`、PAT 只读文件、该空卷；设置 `DSM_PLATFORM=rtd1619b`、`KVM=Y`、`NETWORK=user`、`DISK_SIZE=16G`、2 guest vCPU。容器 `phase4a-kvm-fresh-20261015` 正在运行，完整初次启动串口/日志和实际 QEMU argv 保存在忽略目录 `research/arm64/work/phase4a/boot1.serial.log` 与 `boot1.qemu.argv.txt`。

实际 argv 为 QEMU `qemu-system-aarch64`、`-machine virt,gic-version=3 -accel kvm -cpu host`；没有 TCG accelerator 参数。QEMU 在 2026-10-15T15:39:25Z 启动，生产 QEMU 已在 `/dev/kvm` 上成功启动；实际 guest 到 `Started Serial Getty on ttyS0`、`Reached target Login Prompts` 和 `Reached target Network is Online`。内核正常进入 systemd，未出现 `__no_granule_support` 或相符的 granule/LPA2 故障，因此 KVM CPU gate PASS，分类进至 K2。早期共有启动 banner 曾显示 inherited KVM disabled 警告；它出现在 ARM accelerator 选择前，实际最终 QEMU argv 与 KVM 启动结果为准。

对运行中 QEMU 建立第二个 QMP 客户端并查询 `query-kvm` 超时，QMP 欢迎消息未返回；生产 lifecycle watcher 已持有该 QMP socket 以记录 shutdown 事件，因此没有终止或替换 watcher。实际生产 argv 明确使用 `-accel kvm`，且同一镜像的独立容器探针已取得 monitor `kvm support: enabled`；运行中 QEMU 的独立 `query-kvm` 回执尚未取得。

HTTP 首次观测为 200（2026-10-15T15:41:40Z，QEMU 启动后约 135 秒）；后续探测 HTTP 200、HTTPS 200。DSM 欢迎设置页已打开，等待本地管理员凭据由用户在 stock UI 中输入、确认并提交。尚未声称 configured、PostgreSQL、数据卷、Btrfs、稳定性或 clean shutdown 通过；ttyS1、AHCI/sata1、LED/scemd、XHCI/CDC ECM/eth0 的完整回归核对待配置后继续。Phase 4A 保持 K2；Phase 3 F5 和 Watchdog L5 不变，Phase 3 runtime 跨主机可移植性与 bare-metal ARM64 均为 `UNTESTED`。

## 2026-10-16 first-user setup and StorageManager package

用户通过 DSM stock 欢迎向导设置本地管理员并进入桌面；页面显示 DSM 系统状态“正常”。临时测试凭据仅保存在忽略目录 `research/arm64/work/phase4a/admin-credentials.txt`（mode 0600），后续 K5 完成后清理。没有启用 Synology Account 或 QuickConnect。

重新计算官方 PAT SHA256 后再次通过完全相同的门禁。使用现有 ARM64 生产镜像的 `/run/extract.py` 将 PAT 内容抽取到忽略目录 `research/arm64/work/extracted/`；专有文件不会进入 Git。提取助手因 `-d` 参数探测不兼容而退出，直接按镜像内 `extract.py --help` 所示只支持的 `-d` 调用完成抽取。包中心 stock 上传与非强制签名/依赖检查通过，安装了 PAT 自带的 `StorageManager-rtd1619b-1.0.0-00502.spk`（系统安装包）。

DSM 只读 Storage API 报告唯一内部磁盘 `sata1` / Drive 1、16 GiB、状态 `not_use`，无存储池，Volume API `total=0`。bootstrap `SYNO.Core.Desktop.SessionData/getjs` 仍报告 `configured=false`、`dsm_upgrade_all_done=false`、`dsm_upgrade_pgsql_status=failed`；因此进入桌面和包安装不能计作 K3。待通过 DSM stock Storage Manager 向导在此单盘创建 Basic/Btrfs volume，再复核实际挂载、configured、PostgreSQL 与服务状态。容器 `phase4a-kvm-fresh-20261015` 持续 healthy；现有空存储卷和正在运行的 DSM 均保留。Phase 4A 仍为 K2；Phase 3 F5 / Watchdog L5 保持不变，Phase 3 跨主机 runtime 可移植性和 bare-metal ARM64 均为 `UNTESTED`。

## 2026-10-16 Basic/Btrfs volume and configured transition

用户在 DSM stock Storage Manager 向导的唯一 16 GiB Drive 1 上创建并应用 Basic、Btrfs volume。创建后只读 Storage API 确认 `/volume1`、`raid_type=basic`、状态 normal、未崩溃、非只读，文件系统容量约 5.93 GB；唯一磁盘 `sata1` 状态 normal 且由 `volume_1` 使用，存储池列表为空。用户随后通过 Control Panel stock 向导在该 Btrfs 空间建立 `phase4a-acceptance` 测试共享文件夹，仅允许管理员组及 `phase4admin` 读写，`guest` 禁止访问；未启用 SMB/NFS 服务。本目录目前只有 DSM 自动建立的 `#recycle`，尚未写入持久化 marker。

第一次 stock UI 正常关机发生于 2026-10-15T16:17:56Z，日志记录 systemd shutdown、`All filesystems unmounted`、`reboot: Power down`，容器/QEMU 返回 0；entrypoint 记录 `clean=true`。这次关机后的第二次冷启动使用相同容器、Docker volume、system image 和生产镜像，容器 started_at 为 2026-10-15T16:18:30Z。启动日志显示 `sata1p3` 被 Btrfs 扫描，之后 PostgreSQL database server/adapter 启动；没有 `__no_granule_support`。实际 `/proc` argv 为 `qemu-system-aarch64 -machine virt,gic-version=3 -accel kvm -cpu host`，含已有生产 `KVM=Y` 启动路径且没有 TCG accelerator；同容器 `/dev/kvm` 可读写、guest/container `uname -m=aarch64`。无盘生产 QEMU monitor 的 KVM-enabled 探针通过记录仍见前节；本次运行独立 QMP `query-kvm` 回执尚未取得。

2026-10-15T16:33:26Z 的匿名 `SYNO.Core.Desktop.SessionData/getjs` 返回 `configured=true`、`dsm_upgrade_all_done=true`、`dsm_upgrade_pgsql_status=active`；本地 HTTP 和 HTTPS 均返回 200，Docker healthcheck 为 healthy。忽略目录 `boot2-bootstrap.json` 保存该状态；完整串口快照和 `/proc/212/cmdline` 分别保存在 `boot2-running.serial.log` 与 `boot2.qemu.argv.txt`。第二次启动 HTTP/HTTPS 采样于 2026-10-15T16:24:08Z 至 17:52:18Z 完成 31 组探测，全部 HTTP 200、HTTPS 200，覆盖约 88 分钟；记录位于忽略文件 `boot2-http-30.jsonl`。此结果证明首次配置状态和该窗口内管理面恢复，但不单独满足 K3：登录后仍需复核 Storage Manager 卷、PostgreSQL/scemd/nginx、网卡与路由，并写入和复核持久化 marker。DSM 正常关机后管理员网页会话已过期；本地忽略目录临时凭据登录曾返回 API error 400，已停止重试以避免锁号，需用户手动重新登录 `phase4admin` 才能完成 UI 持久化验收。

用户执行首次 DSM UI 关机后，管理员网页会话过期。忽略目录中的本地临时凭据通过 DSM API 登录返回 Auth error 400，因此停止 API 登录重试，避免触发账户锁定。当时需要用户在 localhost DSM 标签重新登录，才能继续 File Station marker 与 stock UI clean shutdown；该操作在后续验收中完成。此轮没有启动另一个 PAT/DSM build，也没有改生产代码或 watchdog。Phase 3 F5 和 Watchdog L5 保持通过，Phase 3 runtime 跨主机可移植性与 bare-metal ARM64 仍为 `UNTESTED`。

## 2026-10-17 marker persistence and third cold boot

用户在 DSM 登录页手动重新登录后，File Station `phase4a-acceptance` 显示 `phase4-kvm-persistence.txt`，大小 139 bytes；该文件经 DSM File Station UI 上传，内容对应忽略目录中的本地合成 marker。marker 位于 Basic/Btrfs volume 的共享目录 `/volume1/phase4a-acceptance/phase4-kvm-persistence.txt`。随后用户通过 DSM 电源菜单确认第二次 stock UI clean shutdown；2026-10-16T15:59:02Z 容器以 exit 0 退出，serial 记录 `All filesystems unmounted`、`reboot: Power down`，entrypoint 记录 `clean=true`。

同一容器与卷于 2026-10-16T15:59:18Z 第三次冷启动。early serial 到达 `Network is Online`、`Login Prompts`，没有 `__no_granule_support`、panic/Oops、BUG、soft lockup、RCU stall、SError 或 alignment fault。重新登录后的 DSM desktop 显示“正常”；File Station 中同名 139-byte marker 仍存在。Storage Manager 显示系统/存储空间良好，RAID 类别 Basic、Drive 1 16 GB/状态良好；启动串口确认 Btrfs `/dev/sata1p3` 被扫描挂载。只读 `SessionData/getjs` 返回 `configured=true`、`dsm_upgrade_all_done=true`、`dsm_upgrade_pgsql_status=active`。DSM HTTP/HTTPS 与 Docker healthcheck 均恢复 200/healthy。第三次启动生产 QEMU 实际 argv 再次包含 `-accel kvm -cpu host`，同一 ARM64 镜像和 QEMU SHA256 未变；`/dev/kvm` 在容器可读写，没有 TCG 参数或回退。

`boot3.serial.log` 与 `boot3-http-30.jsonl` 留在忽略目录。boot3 HTTP/HTTPS 采样已完成 31 组，全部返回 200，首末采样时间跨度约 50 分钟。第三次冷启动满足配置态、Basic/Btrfs、服务与 marker 的 K3 检查；K4 仍需额外完整 configured lifecycle。

## 第四次冷启动：等待 DSM UI 复核

第四次冷启动使用同一容器、卷、生产镜像和官方 PAT，容器于 2026-10-16T16:57:29Z 启动。忽略目录 `boot4.serial.log`、`boot4-bootstrap-status.txt` 保存证据。容器为 `running/healthy`；guest/container `uname -m=aarch64`，`/dev/kvm` 为 `root:994 0660`；QEMU SHA256 仍为 `55600fc63081177f61b9bf7251e360349fd89a97bc3944007712cd66b6659a20`，实际进程参数含 `-accel kvm -cpu host`，没有 TCG 参数。bootstrap 状态为 `configured=true`、`dsm_upgrade_all_done=true`、PostgreSQL `active`。串口达到网络与登录目标，未发现 granule 错误、panic/Oops、BUG、soft lockup、RCU stall、SError 或 alignment fault；启动早期有一次非致命的本地 user/group DB rebuild dependency warning，之后 Docker 与 HTTP 健康恢复。

用户重新登录后，boot4 File Station 再次显示 `phase4-kvm-persistence.txt`（139 Bytes）；Storage Manager 显示 Basic 存储池良好、Drive 1（16 GB）状态良好，Volume 1 为 Btrfs 且状态良好。随后用户通过 DSM 用户菜单执行第四次 stock UI clean shutdown。2026-10-17T12:15:24Z 容器退出码 0，runtime 收据的 `guest=true`、`reason=guest-shutdown`、`clean=true`；serial 包含 `All filesystems unmounted` 与 `reboot: Power down`，无 host-stop fallback。

第五次冷启动使用同一容器、磁盘、PAT 与生产 ARM64 镜像，始于 2026-10-17T12:15:37Z。忽略目录保存 `boot5.serial.log` 和 `boot5-bootstrap-status.txt`。串口早期到达 `Network is Online` 与 `Login Prompts`，没有 granule 支持故障或内核崩溃/锁死特征。容器内 `uname -m=aarch64`，`/dev/kvm` 可用；QEMU SHA256 不变，实际参数为 `-accel kvm -cpu host`，没有 TCG 参数。Docker healthcheck 与 DSM HTTP/HTTPS 均为 healthy/200。只读 `SessionData/getjs` 返回 `configured=true`、`dsm_upgrade_all_done=true`、PostgreSQL `active`；stock UI 显示系统正常、Basic pool 与 16 GB Drive 1 良好、Btrfs Volume 1 良好，File Station 中 139-byte marker 仍在。boot3、boot4、boot5 三次配置态冷启动均完成 K3 复核；boot3 的 31 组 HTTP/HTTPS 样本全部为 200、覆盖 50.0 分钟；已有三次 marker 创建后的 DSM UI clean shutdown，其中最近两次记录 `guest=true`、`reason=guest-shutdown`、QEMU exit 0、`clean=true`，serial 有完整文件系统卸载与 `reboot: Power down`。因此 Phase 4A K4 lifecycle 稳定门槛通过；结合精确官方 PAT 空盘自动安装与完整配置持久化，Phase 4A 达到 K5。boot5 保持运行。Phase 3 F5、Watchdog L5 保持通过；Phase 3 runtime 跨主机可移植性与 bare-metal ARM64 仍为 `UNTESTED`。

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
