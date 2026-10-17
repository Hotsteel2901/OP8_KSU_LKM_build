#!/system/bin/sh

MODDIR=${0%/*}
LOG=/data/adb/susfs_lkm.log
KO="$MODDIR/susfs_guard_lkm.ko"
TAG="susfs_lkm/service"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$TAG] $*" >> "$LOG" 2>/dev/null; }

if [ -d /sys/module/susfs_guard_lkm ] || grep -q '^susfs_guard_lkm ' /proc/modules 2>/dev/null; then
    exit 0
fi

if [ ! -f "$KO" ]; then
    log "ko not found: $KO"
    exit 0
fi

KSUD=/data/adb/ksud
[ -x "$KSUD" ] || KSUD=$(command -v ksud 2>/dev/null)
if [ -z "$KSUD" ]; then
    log "ksud not found, cannot load $KO"
    exit 0
fi

log "loading $KO via $KSUD"
if "$KSUD" insmod "$KO" >> "$LOG" 2>&1; then
    log "insmod ok"
else
    log "insmod failed (rc=$?)"
fi
exit 0
