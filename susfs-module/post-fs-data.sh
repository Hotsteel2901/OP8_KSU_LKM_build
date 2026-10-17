#!/system/bin/sh

MODDIR=${0%/*}
LOG=/data/adb/susfs_lkm.log
KO="$MODDIR/susfs_guard_lkm.ko"
TAG="susfs_lkm/post-fs-data"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$TAG] $*" >> "$LOG" 2>/dev/null; }

if [ -d /sys/module/susfs_guard_lkm ] || grep -q '^susfs_guard_lkm ' /proc/modules 2>/dev/null; then
    exit 0
fi

if [ ! -f "$KO" ]; then
    log "ko not found: $KO"
    exit 0
fi

find_ksud() {
    if [ -x /data/adb/ksud ]; then
        echo /data/adb/ksud
        return 0
    fi
    command -v ksud 2>/dev/null
}

KSUD=$(find_ksud)

i=0
while [ -z "$KSUD" ] && [ "$i" -lt 20 ]; do
    i=$((i + 1))
    sleep 1
    KSUD=$(find_ksud)
done

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
