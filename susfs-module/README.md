# SUSFS-LKM KernelSU 模块模板

这个目录是打包 **`susfs-lkm-module.zip`** 的模板。工作流在编译出
`susfs_lkm/kernel/susfs_guard_lkm.ko` 之后，会把该 `.ko` 与这里的 `module.prop`、
`post-fs-data.sh`、`service.sh` 一起打成一个 **KernelSU 模块 zip**，并作为构建产物上传。

## 为什么需要它

KernelSU 的 `ksud boot-patch` 只把 `ksu.ko` 注入 boot 的 ramdisk；SUSFS 是**外置
运行时模块**（`susfs_guard_lkm.ko`），不会被打进 boot.img。本模块负责在开机时用
`ksud insmod` 把它加载起来，这样刷完 boot.img 后到管理器里装一次本模块即可。

## 安装

1. 刷入 `boot-patched-kernelsu-ds-rk*.img`（内含 `ksu.ko`）。
2. 在 KernelSU 管理器里安装 `susfs-lkm-module.zip`，或：
   ```sh
   ksud module install /path/to/susfs-lkm-module.zip
   ```
3. 重启。

## 加载时机

- `post-fs-data.sh`：尽量早地加载（`ksud` 就绪后立即 `insmod`）。
- `service.sh`：late_start 兜底（若上一阶段没加载成功再试一次）。

两个脚本都是幂等的：先检查 `/proc/modules` 里是否已有 `susfs_guard_lkm`，已加载则跳过；
任何失败都只写日志、`exit 0`，不会阻塞开机。

## 日志 / 排查

```sh
cat /data/adb/susfs_lkm.log
lsmod | grep susfs
# 手动加载 / 卸载：
ksud insmod /data/adb/modules/susfs_lkm/susfs_guard_lkm.ko
rmmod susfs_guard_lkm
```

> 注意：SUSFS-LKM 在 non-GKI 4.19 上能否 `insmod` 成功仍需真机验证；若失败，
> `/data/adb/susfs_lkm.log` 会记录具体原因（符号解析 / vermagic / CFI 等）。
