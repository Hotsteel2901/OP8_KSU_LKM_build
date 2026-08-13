# OP8_KSU_LKM_build

**OnePlus 8 (instantnoodle / sm8250 / kona) · LineageOS 23.2 (4.19.325) · KernelSU LKM 模式**

自动拉取 [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU) **最新 master 提交**,集成 **LKM(kernelsu.ko + ksud)** + **Re:Kernel** + **DroidSpaces**,产出可 `fastboot` 直刷的 **boot.img(header v2)**。

与 [NonGKI_Kernel_Build_OP8](https://github.com/Hotsteel2901/NonGKI_Kernel_Build_OP8) 的区别:那个是 **ReSukiSU 内建(in-tree)模式** + AnyKernel3;这里是 **纯 LKM 模式**(KernelSU 代码 100% 在 `kernelsu.ko`,运行时加载),且只集成 DS+RK,**不集成** SUSFS / ReSukiSU / Baseband-guard。

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

> **内核"最新"策略**:默认拉 `lineage-23.2` 最新提交。由于 DS/RK 补丁按 `4238ee49a84b` 生成,若最新提交改动过大导致补丁打不上,工作流会**自动回退到 `patch_base`**(已验证基线)再打。两种情况下产物都可用。

## 产物

| 文件 | 说明 |
|---|---|
| `boot-patched-kernelsu-*.img` | **刷这个**。header v2、no-LTO 内核、ramdisk 注入 ksuinit + ksu.ko |
| `ksu.ko` | 与最终内核配置匹配的 LKM 驱动 |

## 集成内容

| 组件 | 说明 |
|---|---|
| **KernelSU LKM** | `backslashxx/KernelSU` 最新 master;`ksu.ko` 外置编译,`ksud` 被打了 v2 补丁(原版只认 v3+ 头) |
| **Re:Kernel** | `Patches/Rekernel/rekernel_extra.patch` + `CONFIG_REKERNEL=y`,`CONFIG_REKERNEL_NETWORK=n` |
| **DroidSpaces** | `Patches/Droidspaces/cgroup.patch`(cgroup 前缀隐藏)+ `droidspaces.config` 全量配置片段 |

## 关键经验(踩过的坑)

### 1. 为什么必须关 LTO/CFI
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

### 7. 构建内存
4.19 全量编译吃内存,`-j4` 在 GitHub runner(16G)足够;本地 7G 机器建议 `-j2`。

## Patches 目录

```
Patches/
├── ksud-v2.patch                    # ksud boot-patch 支持 v2 头
├── Rekernel/
│   └── rekernel_extra.patch         # Re:Kernel 源码(驱动 + binder + signal)
└── Droidspaces/
    ├── cgroup.patch                 # cgroup 前缀隐藏(kernfs_create_link)
    ├── droidspaces.config           # DroidSpaces 内核配置片段
    ├── fix_kernel_panic_in_xt_qtaguid.cocci        # 备用(coccinelle)
    └── fix_restore_cgroup_file_prefix_handling.cocci
```

## 维护

- 内核默认拉最新;DS/RK 补丁基于 `4238ee49a84b` 生成,若最新内核补丁打不上会自动回退到 `patch_base`。长期想跟进最新,可在最新提交上重打补丁并提交更新 `Patches/Rekernel/` 与 `Patches/Droidspaces/cgroup.patch`。
- 管理器侧每次运行都拉最新 master,`ksu.ko`/`ksud`/`ksuinit` 自动跟随。若 manager 源码改了 `boot_patch.rs` 导致 `Patches/ksud-v2.patch` 打不上,工作流会失败,需同步更新该补丁。
- 想集成更多模块,在 `build-lkm.yml` 的 config/补丁步骤后追加即可。

## 致谢

- [Hotsteel2901/NonGKI_Kernel_Build_OP8](https://github.com/Hotsteel2901/NonGKI_Kernel_Build_OP8) - 内核补丁与排障基础
- [JackA1ltman/NonGKI_Kernel_Build_2nd](https://github.com/JackA1ltman/NonGKI_Kernel_Build_2nd) - 工作流参考
- [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU)
- [Re-Kernel](https://github.com/Sakion-Team/Re-Kernel)
- [Droidspaces](https://github.com/ravindu644/Droidspaces-OSS)
- [ReSukiSU](https://github.com/ReSukiSU/ReSukiSU)
- [SuSFS](https://gitlab.com/simonpunk/susfs4ksu)
- [Baseband-guard](https://github.com/vc-teahouse/Baseband-guard)

---

## ksun_lkm 分支:KernelSU-Next 版

本分支额外提供 **`build-lkm-ksunext.yml`** 工作流,把管理器换成 [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next)(最新提交),内核侧(Re:Kernel + DroidSpaces、no-LTO/CFI)与 master 完全一致。

### 使用
1. 切到本分支,`Actions → Build KSUNext LKM Kernel → Run workflow`(基底 boot.img 同 master,仓库内 `base/boot.img`)。
2. 产物 `boot-patched-ksunext-ds-rk` 内含 `kernelsu_next_patched_*.img` + `kernelsu.ko`。
3. 刷机后装 **KSUNext 管理器**(模块内置其签名 `KSU_NEXT_MANAGER_HASH`)。

### KSUNext 在 4.19 上的移植经验(`Patches/ksunext-4.19-compat.patch`)

KernelSU-Next 面向 GKI 5.x+,在 4.19 编译会踩到大量新内核 API。逐文件兼容如下:

| 文件 | 4.19 兼容处理 |
|---|---|
| `infra/file_wrapper.c` | `f_op->iopoll` 需 `>=6.0` 守卫;`remap_file_range`(5.3+)→4.19 用 `dedupe_file_range`(5 参、末参 `u64`、返回 int) |
| `infra/su_mount_ns.c` | `uapi/linux/mount.h` 4.19 不存在,`>=5.12` 才 include |
| `infra/seccomp_cache.c` | 4.19 内核无 seccomp action cache,整体 no-op(`>=5.8` 才实现) |
| `policy/allowlist.c` | `TWA_RESUME`(5.13+)→4.19 `task_work_add(..., true)`;`put_task_struct` 需 `sched/task.h` |
| `policy/app_profile.c` | `seccomp.filter_count`(5.11+)守卫掉 |
| `manager/pkg_observer.c` | fsnotify 用 4.19 老 `handle_event`(8 参)而非 `handle_inode_event`(`>=5.2` 守卫) |
| `selinux/sepolicy.c` | avtab `htable` 在 4.19 是 `flex_array`(用 `avtab_get_slot/set_slot`);`add_filename_trans` 加 `<5.7` 老结构分支(无 stypes,`db->filename_trans_ttypes`);`add_type` 数组在 4.19 全 flex_array,需重建复制;`add_typeattribute` 用 `flex_array_get` |
| `selinux/sepolicy.h/.c` | `ksu_dup_sepolicy/ksu_destroy_sepolicy` 依赖 `struct selinux_policy`(5.5+),`>=5.5` 才声明/定义 |
| `selinux/rules.c` | `apply_kernelsu_rules`/`handle_sepolicy` 用 5.x 的 dup/swap 策略;4.19 改为**就地**改 `selinux_state.ss->policydb`(持 `ss->policy_rwlock` 写锁);`backup_sepolicy` 5.5+ 才有 |
| `feature/selinux_hide.c` | 深度依赖 5.x `backup_sepolicy`/`selinux_policy`,4.19 整体 no-op(`>=5.5` 才实现) |
| `sulog/event.c` | `linux/minmax.h`(5.10+)→4.19 用 `linux/kernel.h` |
| `supercall/dispatch.c` | `tasklist_lock`/`task_pgrp`/`task_session`/`init_task` 需显式 include |
| `supercall/supercall.c` | `TWA_RESUME`(5.13+)→`true` |

关键结论:
- **`selinux_state` 布局差异是最大坑**:4.19 的 `status_lock/status_page/policydb/policy_rwlock` 全在 `struct selinux_ss`(`selinux_state.ss->...`),5.5+ 才搬到顶层。
- **SELinux 策略写入**:5.x 用 dup→改→rcu swap;4.19 只能拿 `ss->policydb` 就地改 + `write_lock(ss->policy_rwlock)` + `reset_avc_cache()`。
- **flex_array**:4.19 的 avtab/policydb 数组全是 `struct flex_array *`,不可 resize,只能新建复制。
- KSUNext 的 ksud 没有 `--module` 短路(backslashxx 有),boot-patch 必须显式传 `--kmi` 跳过 KMI 自动探测(4.19 非 GKI 探测会失败)。
- 兼容补丁基于 KSUNext commit `234f6e04`;上游移动后若补丁打不上,在最新提交上重打并更新 `Patches/ksunext-4.19-compat.patch`。
