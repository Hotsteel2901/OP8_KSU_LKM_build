# SUSFS-LKM 的 4.19 适配

本目录用于把 **SUSFS 做成可加载内核模块（LKM）** 的源码适配到 OnePlus 8 的
**4.19.325 non-GKI（LineageOS 23.2 / kona-perf_defconfig）**。

- 源码来源：`https://github.com/Hotsteel2901/susfs4ksu-lkm`（fork 自 `inforcqb/susfs4ksu-lkm`），
  分支 **`legacy`**（上游为 pre-5.10 准备的移植起点）。
- 构建方式：`build-lkm.yml` 里克隆 `legacy` 分支，然后按文件名顺序应用本目录的 `*.patch`。
- 工作目录里的 `*.patch` 会在克隆后、构建前应用（`patch -p1`）；失败即整条构建失败。

> ⚠️ 上游 `legacy` 分支**明确声明未构建、未测试、无二进制**（`LEGACY_PORTING.md`）。
> 本目录的补丁是 4.19 适配的产物：以编译报错为输入逐条补齐。
>
> **当前状态（本地已验证）**：在 lineage-23.2 的 4.19 树上（defconfig + oplus + droidspaces
> + `KPROBES/KRETPROBES`）**完整编译通过，0 error**，产出
> `fs/susfs_guard_lkm.o` → `susfs_guard_lkm.ko`（clang-14 实测；CI 用 clang-18）。
> 加载/运行期（ksud 解析符号 + 真机功能）仍需真机验证。

## 为什么这条路对我们的价值

我们本来就在编内核，LKM 的意义不是「省编译」，而是**让 SUSFS 与内核构建解耦**：
SUSFS 可以独立升级、不依赖 in-tree SUSFS 补丁。
加载链复用 KernelSU 的 ksud：它会用 `/proc/kallsyms` 预解析未定义符号并改写 vermagic，
这正是 SUSFS-LKM 「运行时解析符号」所依赖的机制。

## 我们内核的硬前提（已核对 kona-perf_defconfig）

| 需求 | 状态 | 处理 |
|---|---|---|
| `CONFIG_MODULES` / `MODULE_UNLOAD` | ✅ y | — |
| `CONFIG_KALLSYMS_ALL` | ✅ y | 符号可解析 |
| `CONFIG_SECURITY` / `SECURITY_SELINUX` | ✅ y | LSM 层在 |
| `CONFIG_MODVERSIONS` | ⚠️ y | 对树编译即可；未定义符号由 loader 绕过 |
| `CONFIG_LTO_CLANG` | ⚠️ y | 构建时**关闭**（改 `LTO_NONE`） |
| `CONFIG_CFI_CLANG` | 无 | ✅（无 CFI，原型不符不会 panic） |
| `RANDSTRUCT` | 无 | ✅（`security_hook_heads` 可按偏移读取） |
| **`CONFIG_KPROBES` / `KRETPROBES`** | ❌ 未启用 | 构建时**开启**（dirent 过滤 + 符号自举） |

## 4.19 适配地图（来自上游 `LEGACY_PORTING.md`，映射到本内核）

### A. 机械 shim（上游 legacy 分支已提供，无需我们改）
`kernel/susfs.h` 的 `< 5.10` gate：`proc_ops→file_operations`(<5.6)、
`copy_{from,to}_kernel_nofault→probe_kernel_{read,write}`(<5.8)、
`MODULE_IMPORT_NS` 置空(<5.4)、`__nocfi` 置空(<5.10)。

### B. 必须真改（本目录补丁的落点）
1. **`task_work_add`**：4.19 是 `(task, work, bool notify)`；上游用 `TWA_RESUME`(5.x)。
   映射为 `notify=false`（语义更接近 `TWA_RESUME`）。落点 `kernel/susfs_supercall.c`。
2. **挂载表迭代**：上游 ≥6.12 用 `rb_first(&ns->mounts)`；4.19 是 `ns->list`（list_head）
   且无 `mnt_ns_attached()`。落点 `kernel/sus_mount.c` 的 `SUS_MOUNT_ITER_FOR` /
   `SUS_MOUNT_MNT_NOT_IN_NS` 宏。
3. **LSM hook 定义位置/形状**：4.19 用 `include/linux/lsm_hooks.h`（不是 5.x 的
   `lsm_hook_defs.h`），`struct security_hook_list` 形状不同。落点 `kernel/lsm_hook.c` /
   `kernel/sus_path.c` 的 `KSU_LSM_HOOK_INSERT` 与静态断言。
4. **移除不存在的 hook**：`path_notify`(5.2) 在 4.19 **不存在**，必须从 hook 列表与
   静态断言里删掉。
5. **符号集审计**：`nm -u susfs_guard_lkm.ko` 的每个名字都要在 `vmlinux`/`System.map`
   里（如 Android 专有 `sized_strscpy` 4.19 未必有）。构建日志里会打印未定义符号。

### C. 加载/加载器（最容易出问题）
- GKI 世界用 loader 从 `/proc/kallsyms` 绝对化未定义符号、绕过 export/CRC/KMI。
  4.19 上走 **KernelSU 的 `ksud insmod`**（backslashxx/KernelSU 已验证同一机制）。
- 我们的内核 `MODVERSIONS=y`：对树编译得到的 CRC 一致；未定义符号由 loader 绕过。

### D. 运行时验证（真机，来自上游 §5）
1. loader 打印 `resolved N/N; unresolved 0` 且退出码 0；
2. `[ -d /sys/module/susfs_guard_lkm ]`（`lsmod`/`/proc/modules` 看不到是设计）；
3. 计数器 `/sys/module/susfs_guard_lkm/parameters/{hide_list,mount_stat}` 必须随
   非 root 读取隐藏路径而动；
4. 两次 `rmmod` 返回 0 且 `dmesg` 无 alarm；
5. 加载即重启时要收 `/sys/fs/pstore/console-ramoops-0`（kCFI 原型不符会 panic；
   4.19 无 CFI，风险主要在文本补丁/结构体布局）。

## 已应用补丁

按 CI 编译错误逐条补齐（工作流按文件名顺序应用）：

| 补丁 | 解决问题 |
|---|---|
| `0001-susfs_h-...` | `susfs.h` 集中补 `<5.10/5.5/5.7` 兼容：`regs_set_return_value()`（4.19 arm64 无，`sus_map`/`sus_path`/`susfs_hide_syms` 用）、`TWA_RESUME`（`susfs_supercall.c` 的 `task_work_add`）、`regs_get_kernel_argument()`（`sus_path.c`/`susfs_hide_syms.c` 用，4.19 无）、以及 `<linux/ratelimit.h>`（4.19 的 `printk.h` 不包含它，`*_ratelimited` 会展开失败）。 |
| `0004-sus_mount-419-mount-layout-and-statx.patch` | `sus_mount.c` 的 `fs/mount.h` 布局与 statx 差异：4.19 的 `struct mnt_namespace` **无 `ns_lock`**、无 `MNT_CURSOR`（`ns->list` 仍在）→ 新增 `< 5.7` 子分支（用 no-op 锁宏 + 去掉 cursor 判定，并把两处 `spin_lock(&ns->ns_lock)` 换成 `SUS_MOUNT_NS_LOCK(ns)`）；`struct statx` **无 `stx_mnt_id`**（5.8+）→ 门控掉 statx 的 mnt_id 改写（门控分支里把 `id/shown/new_id` 用 `(void)` 标记，避免 `-Wunused-variable` 报错）。 |
| `0002-sus_path-drop-path_notify-pre52.patch` | `path_notify` 是 5.2+ 的 LSM hook，4.19 的 `security_hook_heads`/`security_list_options` 没有该成员。按 `>= 5.2` 门控掉该 hook（前向声明、静态断言、hook 结构体、处理函数、注册/注销列表项），4.19 上不安装它。 |
| `0003-susfs_kstat-syscall_get_arguments-5args.patch` | 本 4.19 树的 arm64 `syscall_get_arguments` 是 **5 参**形式 `(task, regs, i, n, args)`，而源码用的是 3 参。改为 `(current, regs, 0, 6, args)`。 |

## 迭代方式

- 每次跑 `build-lkm.yml` → 看 `Build SUSFS-LKM` 失败时打出的 `::error::` 编译错误 →
  在本目录加/改补丁 → 重跑。
- 本目录的 `*.patch` 会在克隆 `susfs_lkm` 之后、构建之前按文件名顺序 `patch -p1` 应用；失败即整条构建失败。
- 上游仍在活跃修 dirent/kprobe（`fix/dirent-buffer-residue`、`fix/kprobe-rearm`），
  跟进时注意 `susfs_lkm_ref` 固定到具体 commit 更可复现。
