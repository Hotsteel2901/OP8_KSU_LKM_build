# 变更存档 / Patches Archive

本目录记录对补丁与工作流的**结构性变更**及其原因、验证方式与踩坑。每次大改追加一节，不删旧记录。

---

## 2026-10-05:上游核对 + Re:Kernel → ReKernel-X + VFS 后端开关

### 1. 上游核对结论（全部实测，非推断）

| 组件 | 上游 | 结论 |
|---|---|---|
| Re:Kernel (`Sakion-Team/Re-Kernel`) | `ac08296` (2026-09-20) | **整体替换为 ReKernel-X**（见下）。旧 `rekernel_extra.patch` 的内嵌源码与上游 Integrate 版基本逐字节一致，且含两处本地更优修正（`static` 收敛符号导出、补 `<linux/sched/jobctl.h>` include——正是上游 README 提示的已知坑），但已弃用 |
| ReKernel-X | `Patches/RekernelX/rkx-4.19.patch`（本组织 4.19 移植版，源自 NonGKI_Kernel_Build_OP8） | 新采用。改 `binder.c`/`binder_alloc.c`/`kernel/signal.c` + 新增 `drivers/rekernel_x/`（12 文件）；Kconfig/Makefile 接线 hunk 已从补丁剔除，由工作流手动完成（避免与其他步骤对 `drivers/Kconfig` 的文本注入互相踩） |
| DroidSpaces cgroup 补丁 | 上游 `02.fix_restore cgroup file prefix handling .patch`（2026-02-22 起未改） | 与本地 `cgroup.patch` 语义等价（仅缩进规范化），不更新 |
| DroidSpaces config | 上游 `Documentation/Kernel-Configuration.md` 已扩充 | **补齐 8 项**：`CFS_BANDWIDTH`、`CGROUP_CPUACCT`、`IPV6`、`IPV6_MULTIPLE_TABLES`、`IP6_NF_IPTABLES/FILTER/MANGLE/NAT/TARGET_MASQUERADE`。注意：上游还列了 `NF_CONNTRACK_IPV6`/`NF_NAT_IPV6`，但这两个符号在 4.19 **不存在**（4.18 起 nf_conntrack_ipv6/nf_nat_ipv6 已并入通用 nf_conntrack/nf_nat），写入是 no-op，故省略并注释说明 |
| `ksud-v2.patch` | backslashxx `148139e`（KSU_VERSION 32657） | `boot_patch.rs:enforce_bootimage_version` 目标代码逐字未变，dry-run RC=0，**不更新** |
| `xt_qtaguid` 相关 | — | **删除死文件** `fix_kernel_panic_in_xt_qtaguid.cocci`：本内核（sm8250 kona）根本没有 `net/netfilter/xt_qtaguid.c`，补丁无从应用；workflow 从未自动应用过它（原步骤自己写明 "not auto-applied"） |
| 内核 lineage-23.2 | `98a7970af93b` (2026-10-04) | 基线 `4238ee49a84b` 落后约 1200 提交，但 RKX/DS 补丁在最新树上实测仍干净应用（`binder.c` 仅 17 行 offset，0 fuzz 0 reject），`patch_base` 回退机制本次保留不动 |

### 2. Re:Kernel → ReKernel-X 替换

- 两套补丁都改 `drivers/android/binder.c`，**互斥**，必须替换而非叠加。
- config：`CONFIG_REKERNEL=y` + `CONFIG_REKERNEL_NETWORK=n` → `CONFIG_REKERNEL_X=y`（rkx 无独立 network 开关，netfilter/netuid 对象随主模块一起编）。
- 事件通道：Generic Netlink family `rekernel_x2`（旧 Re:Kernel 是自己的 proc/netlink 方案），用户空间接收端需配套 ReKernel-X。
- **实测**：4238ee49a84b 干净树上 0 offset 应用；`CONFIG_REKERNEL_X=y` 后 `make drivers/rekernel_x/` 全部 8 个 .o + `built-in.a` 编译通过，0 错误。

### 3. VFS 后端开关（HybridMount / NoMount，二选一，默认关）

实现：

- 新增 `workflow_dispatch` 输入 `vfs_hybridmount` / `vfs_nomount`（默认 `false`）。
- 新增 `Validate VFS backend selection` 步骤：互斥校验（>1 立即 fail）+ 组产物后缀 `VFS_LABEL`（`-hybridmount` / `-nomount` / 空）写入 `$GITHUB_ENV`，Upload 步骤用 `boot-patched-kernelsu-ds-rk${{ env.VFS_LABEL }}` 命名。
- HybridMount：内置补丁 `Patches/HybridMount/hybridmount_patch_to_4.19.patch`（复用 NonGKI_Kernel_Build_OP8 的已验证版本，5 个纯新增文件 + fs/Kconfig、fs/Makefile 各一处接线）。应用后 `.rej` 检查 + 三重校验（源文件 / Makefile 接线 / Kconfig 接线）。
- NoMount：在线 `curl .../kernel/setup.sh | bash -s "$NOMOUNT_COMMIT"`，**commit 固定**为 `a159c0c225e67f180b7fb55ad78a77b0f98beb5b`（2026-10-04 dev HEAD）——上游几乎每日提交，跟 dev 头会让构建不可复现。该 commit 已实测：setup.sh 在本内核树正常落 symlink + 双接线。
- 配置注入：在 `merge_config.sh` 之后、`olddefconfig` **之前**，按 `VFS_LABEL` 分支追加：
  - 共同硬依赖：`CONFIG_KEYS=y`（keyring `register_key_type`）、`CONFIG_ASSOCIATIVE_ARRAY=y`（KEYS select 它，显式写出防将来 `FS_ENCRYPTION` 关闭时连带丢失）
  - `CONFIG_HYBRIDMOUNT=y` 或 `CONFIG_NOMOUNT=y`
  - 4.19 无预编译 .ko，两后端必须 built-in
  - `olddefconfig` 后逐项 grep 校验，写错符号名不会静默跳过
- **实测**（真实 4.19 树，kona-perf_defconfig + oplus + droidspaces + no-LTO/CFI 链）：
  - HybridMount：补丁 0 rej 0 fuzz，`fs/hybridmount/hybridmount.o` 编译通过（311KB ARM64 ELF，0 错误 0 警告）
  - NoMount：`fs/nomount/nomount.o` 编译通过（0 错误）
  - 端到端模拟：按 CI 精确顺序执行 RKX → HM → config 三步（脚本从 YAML 原样提取），`CONFIG_HYBRIDMOUNT=y`/`CONFIG_KEYS=y` 全部 stick，新增 droidspaces config 项确认生效

### 4. 踩坑记录

| 坑 | 说明 |
|---|---|
| **VFS 步骤必须在 ReKernel-X 步骤之后** | RKX 步骤的 fallback 逻辑跑 `git clean -fd`，会把先打的 VFS 补丁产物（`fs/hybridmount/`、`fs/nomount` 链接、`NoMount/` 这些未跟踪文件）全部清掉。VFS 打补丁必须在内核 commit 定型（fallback 结束）之后 |
| **VFS CONFIG 必须在 olddefconfig 之前写入** | 这些符号在 defconfig 里没有被引用，olddefconfig 会丢 orphan symbol；先写进 .config 再 olddefconfig 才保留。写入位置在 .config 末尾会有 kconfig "override: reassigning" 警告，属正常（kconfig 取最后一个值） |
| **`make O=` 要求源树绝对干净** | 源树里只要有 in-tree 构建残留（`include/config/`、`arch/*/include/generated/`、`scripts/basic/fixdep` 等，gitignore 所以 `git status` 看不见），O= 构建就会以各种诡异方式失败（本机复现：`asm/types.h not found`）。清理用 `git clean -fdx`。**CI 全新 clone 无此问题**；本地复测务必先 clean |
| **上游 NM `NF_CONNTRACK_IPV6` 符号不存在** | 上游文档在 4.19 上照抄会写入无效配置项，已在本仓库 config 里注释说明 |
| coccinelle 死文件 | 从上游搬 `.cocci` 文件不代表能用：Coccinelle 需要单独安装且从未进工作流。能用的是上游已转正的 `.patch` |

### 5. 回归验证清单（后续改动照此执行）

1. `/tmp/actionlint -oneline .github/workflows/build-lkm.yml` — 工作流静态校验
2. 从 YAML 提取 run 块逐个 `bash -n` — shell 语法
3. 干净 4.19 树：RKX + cgroup 干跑/实跑 → `CONFIG_REKERNEL_X=y` → `make drivers/rekernel_x/`
4. 同树：HM 补丁 0 rej → `CONFIG_HYBRIDMOUNT=y` → `make fs/hybridmount/`；NM setup.sh 固定 commit → `CONFIG_NOMOUNT=y` → `make fs/nomount/`
5. CI 双跑：`vfs_hybridmount=true` 与 `vfs_nomount=true` 各出一份 boot.img
