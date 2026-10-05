# OP8_KSU_LKM_build

**OnePlus 8 (instantnoodle / sm8250 / kona) · LineageOS 23.2 (4.19.325) · KernelSU LKM 模式**

自动拉取 [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU) **最新 master 提交**,集成 **LKM(kernelsu.ko + ksud)** + **ReKernel-X** + **DroidSpaces**,可选 **VFS 后端**(HybridMount / NoMount 二选一,默认关),产出可 `fastboot` 直刷的 **boot.img(header v2)**。

---

## 使用

1. Fork 本仓库,启用 Actions(`Settings → Actions → General → Workflow permissions: Read and write`)。
2. 准备基底 boot.img(**header v2**):
   - 仓库已内置 `base/boot.img`(LOS 23.2 kebab 官方 ramdisk+dtb),**默认直接用,`boot_img_url` 可不填**;
   - 想用自己的基底,Run workflow 时在 `boot_img_url` 填直链即可覆盖。
   - 基底用于提供 **ramdisk + dtb + AVB footer**,内核会被替换,ramdisk 会被注入 ksud/ksu.ko。
3. `Actions → Build Non-GKI LKM Kernel → Run workflow`。
4. 下载产物 `boot-patched-kernelsu-ds-rk`,刷机:
   ```bash
   fastboot flash boot boot-patched-kernelsu-*.img
   fastboot reboot
   ```
5. 开机后安装 backslashxx 管理器 APK(**release 版即可**,签名与 ksu.ko 内置校验一致)。

### 输入参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `boot_img_url` | 空(用仓库内置 `base/boot.img`) | 基底 boot.img 直链,覆盖默认基底 |
| `kernel_commit` | `lineage-23.2` | **内核拉取的分支/提交,默认最新**;想锁版本填 commit SHA |
| `patch_base` | `4238ee49a84b` | DS/RK 补丁在最新内核上打失败时的**自动回退基线** |
| `manager_ref` | `master` | backslashxx/KernelSU 的拉取引用(默认最新 master) |
| `vfs_hybridmount` | `false` | **VFS 后端: Hybrid Mount**(与 NoMount 互斥,最多开一个) |
| `vfs_nomount` | `false` | **VFS 后端: NoMount**(与 Hybrid Mount 互斥,最多开一个) |

> **内核"最新"策略**:默认拉 `lineage-23.2` 最新提交。由于 DS/RK 补丁按 `4238ee49a84b` 生成,若最新提交改动过大导致补丁打不上,工作流会**自动回退到 `patch_base`**(已验证基线)再打。两种情况下产物都可用。

## 产物

| 文件 | 说明 |
|---|---|
| `boot-patched-kernelsu-ds-rk[-hybridmount\|-nomount].img` | **刷这个**。header v2、no-LTO 内核、ramdisk 注入 ksuinit + ksu.ko。产物名后缀标明本次集成的 VFS 后端,没有后缀 = 纯净内核 |
| `ksu.ko` | 与最终内核配置匹配的 LKM 驱动 |

## 集成内容

| 组件 | 说明 |
|---|---|
| **KernelSU LKM** | `backslashxx/KernelSU` 最新 master;`ksu.ko` 外置编译,`ksud` 被打了 v2 补丁(原版只认 v3+ 头) |
| **ReKernel-X** | `Patches/RekernelX/rkx-4.19.patch`(4.19 移植版)+ `CONFIG_REKERNEL_X=y`;Kconfig/Makefile 接线由工作流手动完成 |
| **DroidSpaces** | `Patches/Droidspaces/cgroup.patch`(cgroup 前缀隐藏)+ `droidspaces.config` 全量配置片段 |
| **VFS 后端(可选)** | HybridMount **或** NoMount 二选一,默认都关;见下节 |


## VFS 后端开关(HybridMount / NoMount)

Run workflow 时可选,**二选一,默认都关**:

| 后端 | 上游 | 集成方式 | CONFIG | keyring 协议 |
|---|---|---|---|---|
| **Hybrid Mount** | [Hybrid-Mount/meta-hybrid_mount](https://github.com/Hybrid-Mount/meta-hybrid_mount)(vfs 子系统 fork 自 NoMount,快照 `016375cd`) | 内置补丁 `Patches/HybridMount/hybridmount_patch_to_4.19.patch`(4.19 移植版) | `CONFIG_HYBRIDMOUNT=y` | `"hm1"` / magic `HYBRIDMO` |
| **NoMount** | [maxsteeel/nomount](https://github.com/maxsteeel/nomount) | 在线 `kernel/setup.sh`,**固定 commit**(见工作流 `NOMOUNT_COMMIT`) | `CONFIG_NOMOUNT=y` | `"NOMOUNT"` |

要点:

- **互斥**:两者劫持同一层 VFS(`inode_operations` / `file_operations` / `dentry_operations`)且 keyring 协议互不兼容,同时开会互抢 hook、元模块无法握手。工作流前置校验,开两个直接 fail。
- **必须 built-in(`=y`)**:上游只提供 5.10/5.15/6.1/6.6/6.12 预编译 `.ko`,4.19 属 legacy,无现成模块。共同硬依赖 `CONFIG_KEYS=y`(+其 select 的 `CONFIG_ASSOCIATIVE_ARRAY=y`)。
- **与 LKM 模式无冲突**:VFS 后端是内核内置子系统,`CONFIG_KSU=m` 的外置 `ksu.ko` 照常工作。
- 两者都是内核路径重定向方案(不真挂载文件系统),配合各自的用户空间元模块使用。本工作流只负责内核侧,元模块/APK 请自备。
- 两个后端的 4.19 集成均已在真实内核树上实测编译通过(`fs/hybridmount/hybridmount.o` / `fs/nomount/nomount.o`,0 错误)。

## 坑

### 1. 必须关 LTO/CFI
`kona-perf_defconfig` 里有 `CONFIG_LTO_CLANG=y` / `CONFIG_CFI_CLANG=y`。**官方 LOS 构建用 `LD=ld.lld`(`LLVM=1`)→ CFI 生效**,而普通方式编出的非 CFI `ksu.ko` 在 CFI 内核上**第一次间接调用就 panic**。本工作流强制:
```
scripts/config --file out/.config -e LTO_NONE -d LTO_CLANG -d THINLTO -d CFI_CLANG -d CFI_CLANG_SHADOW
```
(SCS 可保留,GKI 也开,`ksu.ko` 编译时移除了 `-fsanitize=shadow-call-stack`,兼容。)

### 2. `CC=clang` 必须作为 make 命令行参数
内核 Makefile 里 `CC = $(CROSS_COMPILE)gcc` **会覆盖环境变量**。所以所有 make 命令都是 `make CC=clang ...`(命令行),不能用 `export CC=clang`。

### 3. `merge_config.sh` 的 CC 传递
`merge_config.sh` 内部会再调一次 make,必须通过 `MAKEFLAGS="CC=clang ARCH=arm64 ..."` 环境变量注入。

### 4. ksud 的 boot header v2 限制
backslashxx 的 ksud 在 `boot_patch.rs:enforce_bootimage_version` 硬性要求 **header ≥ v3**,而 OnePlus 8 是 **v2**。本仓库 `Patches/ksud-v2.patch` 改为允许 v2(仍拒绝 >4),底层 `android_bootimg` 解析/打包器本身完整支持 v2(含 dtb 块、AVB footer 保留)。

### 5. 修 boot.img 的完整链路
```
基底 boot.img(v2) --[tools/swap_kernel.py 换内核,保留 ramdisk/dtb/AVB]--> swapped.img
swapped.img --[ksud boot-patch 注入 ksuinit + ksu.ko]--> 最终 boot.img
```
- `swap_kernel.py` 纯 Python,与 `android_bootimg` Rust patcher 输出**逐字节一致**(AVB footer 的 `original_image_size`/`vbmeta_offset` 为 **big-endian**,块按 page_size=4096 对齐)。
- ksud 需要先编好 `aarch64-unknown-linux-musl` 的 `ksuinit` 并放到 `userspace/ksud/bin/aarch64/`,再编 ksud(宿主)才会内嵌该资产。
- 加载时 ksud 会用 `/proc/kallsyms` 预解析未定义符号并**自动改写 vermagic**,所以内核本地版本差异(-dirty)无影响。

### 6. 内核准备顺序(外置模块编译前提)
```
make modules_prepare          # 生成 scripts / autoconf.h / Module.symvers
make init/version.o           # 生成 include/generated/compile.h
make security/selinux/avc.o   # 生成 security/selinux/flask.h
```
`flask.h` 缺失会直接报 `fatal error: 'flask.h' file not found`。

## Patches

```
Patches/
├── ksud-v2.patch                    # ksud boot-patch 支持 v2 头
├── RekernelX/
│   └── rkx-4.19.patch               # ReKernel-X 4.19 移植(binder/alloc/signal + drivers/rekernel_x)
├── HybridMount/
│   └── hybridmount_patch_to_4.19.patch  # Hybrid Mount 4.19 移植(5 新文件 + fs 接线)
├── Droidspaces/
    ├── cgroup.patch                 # cgroup 前缀隐藏(kernfs_create_link)
    ├── droidspaces.config           # DroidSpaces 内核配置片段(含 IPv6 NAT66)
    └── fix_restore_cgroup_file_prefix_handling.cocci  # 对照用(coccinelle)
└── Archive/
    └── README.md                    # 变更存档与踩坑记录
```

## 维护

- 内核默认拉最新;RKX/DS 补丁基于 `4238ee49a84b` 生成(在 2026-10-04 最新提交上实测仍干净应用,仅 binder.c 有 17 行 offset),若最新内核补丁打不上会自动回退到 `patch_base`。长期想跟进最新,可在最新提交上重打补丁并提交更新 `Patches/RekernelX/` 与 `Patches/Droidspaces/cgroup.patch`。
- NoMount 集成锁在固定 commit(工作流 `NOMOUNT_COMMIT`),上游更新后想跟进:在内核树跑一次新 commit 的 `kernel/setup.sh` 验证接线,再更新 `NOMOUNT_COMMIT`。
- 管理器侧每次运行都拉最新 master,`ksu.ko`/`ksud`/`ksuinit` 自动跟随。若 manager 源码改了 `boot_patch.rs` 导致 `Patches/ksud-v2.patch` 打不上,工作流会失败,需同步更新该补丁。
- 想集成更多模块,在 `build-lkm.yml` 的 config/补丁步骤后追加即可。

## 致谢

- [Hotsteel2901/NonGKI_Kernel_Build_OP8](https://github.com/Hotsteel2901/NonGKI_Kernel_Build_OP8) - 内核补丁与排障基础
- [JackA1ltman/NonGKI_Kernel_Build_2nd](https://github.com/JackA1ltman/NonGKI_Kernel_Build_2nd) - 工作流参考
- [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU)
- [Re-Kernel / ReKernel-X](https://github.com/Sakion-Team/Re-Kernel)
- [Hybrid Mount](https://github.com/Hybrid-Mount/meta-hybrid_mount)
- [NoMount](https://github.com/maxsteeel/nomount)
- [Droidspaces](https://github.com/ravindu644/Droidspaces-OSS)
- [ReSukiSU](https://github.com/ReSukiSU/ReSukiSU)
- [SuSFS](https://gitlab.com/simonpunk/susfs4ksu)
- [Baseband-guard](https://github.com/vc-teahouse/Baseband-guard)
