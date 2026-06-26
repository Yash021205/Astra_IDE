#!/usr/bin/env python3
"""Parse a first-party Tetragon syscall corpus (/tmp/corpus.json) into per-pod,
per-PID ordered syscall-name sequences. Emits /tmp/seqs.json:

    {"meta": {...}, "by_class": {"wl1": [[id,...], ...], "wl2": [...], "wl3": [...]},
     "syscall_ids": {"__x64_sys_write": 0, ...}}

Each inner list is one PID's time-ordered syscall stream (a "trace"). The B4 IDS
windows these into fixed-length sub-sequences before embedding.
"""
import json
from collections import defaultdict, Counter

CORPUS = "/tmp/corpus.json"
OUT = "/tmp/seqs.json"

pod_counts = Counter()
syscall_ids = {}
# per (pod, pid) -> list of (time, syscall_id) so we can order then strip time
by_pid = defaultdict(list)


def sid(name: str) -> int:
    if name not in syscall_ids:
        syscall_ids[name] = len(syscall_ids)
    return syscall_ids[name]


n = 0
with open(CORPUS) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        pk = o.get("process_kprobe")
        if not pk:
            continue
        n += 1
        proc = pk.get("process", {})
        pod = (proc.get("pod") or {}).get("name", "<none>")
        pod_counts[pod] += 1
        if not pod.startswith("wl"):
            continue
        pid = proc.get("pid", 0)
        fn = pk.get("function_name", "?")
        t = pk.get("process", {}).get("start_time", "") + str(pk.get("pid", ""))
        # order within a pid by event arrival (file order is already time order)
        by_pid[(pod, pid)].append(sid(fn))

by_class = defaultdict(list)
for (pod, pid), seq in by_pid.items():
    if len(seq) >= 2:
        by_class[pod].append(seq)

meta = {
    "total_kprobe_events": n,
    "top_pods": pod_counts.most_common(8),
    "classes": {k: {"pids": len(v), "syscalls": sum(len(s) for s in v)}
                for k, v in by_class.items()},
    "syscall_vocab": len(syscall_ids),
}
with open(OUT, "w") as f:
    json.dump({"meta": meta, "by_class": by_class, "syscall_ids": syscall_ids}, f)

print(json.dumps(meta, indent=2))
print("wrote", OUT)
