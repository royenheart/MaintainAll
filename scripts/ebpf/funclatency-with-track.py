#!/usr/bin/python3
# Edit from BCC project's funclatency
# 1. 统计每个函数的执行时间统计
# 2. 跟踪每个函数的执行时间在时间点上的分布
# @lint-avoid-python-3-compatibility-imports
#
# funclatency   Time functions and print latency as a histogram.
#               For Linux, uses BCC, eBPF.
#
# USAGE: funclatency [-h] [-p PID] [-i INTERVAL] [-T] [-u] [-m] [-F] [-r] [-v]
#                    pattern
#
# Run "funclatency -h" for full usage.
#
# The pattern is a string with optional '*' wildcards, similar to file
# globbing. If you'd prefer to use regular expressions, use the -r option.
#
# Without the '-l' option, only the innermost calls will be recorded.
# Use '-l LEVEL' to record the outermost n levels of nested/recursive functions.
#
# Copyright (c) 2015 Brendan Gregg.
# Copyright (c) 2021 Chenyue Zhou.
# Licensed under the Apache License, Version 2.0 (the "License")
#
# 20-Sep-2015   Brendan Gregg       Created this.
# 06-Oct-2016   Sasha Goldshtein    Added user function support.
# 14-Apr-2021   Chenyue Zhou        Added nested or recursive function support.

from __future__ import print_function
try:
    from bpfcc import BPF  # type: ignore
    from bpfcc.table import PerCpuHash  # type: ignore
except ImportError:
    try:
        from bcc import BPF
        from bcc.table import PerCpuHash
    except ImportError as e:
        print(f"Cant import bcc lib: {e}", file=sys.stderr)
        exit(1)
from time import sleep, strftime
import argparse
import signal
import ctypes
import os
import sys
import asyncio

# arguments
examples = """examples:
    ./funclatency do_sys_open       # time the do_sys_open() kernel function
    ./funclatency c:read            # time the read() C library function
    ./funclatency -u vfs_read       # time vfs_read(), in microseconds
    ./funclatency -m do_nanosleep   # time do_nanosleep(), in milliseconds
    ./funclatency -i 2 -d 10 c:open # output every 2 seconds, for duration 10s
    ./funclatency -mTi 5 vfs_read   # output every 5 seconds, with timestamps
    ./funclatency -p 181 vfs_read   # time process 181 only
    ./funclatency 'vfs_fstat*'      # time both vfs_fstat() and vfs_fstatat()
    ./funclatency 'c:*printf'       # time the *printf family of functions
    ./funclatency -F 'vfs_r*'       # show one histogram per matched function
"""
parser = argparse.ArgumentParser(
    description="Time functions and print latency as a histogram",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=examples)
parser.add_argument("-p", "--pid", type=int,
    help="trace this PID only")
parser.add_argument("-i", "--interval", type=int,
    help="summary interval, in seconds")
parser.add_argument("-d", "--duration", type=int,
    help="total duration of trace, in seconds")
parser.add_argument("-T", "--timestamp", action="store_true",
    help="include timestamp on output")
parser.add_argument("-u", "--microseconds", action="store_true",
    help="microsecond histogram")
parser.add_argument("-m", "--milliseconds", action="store_true",
    help="millisecond histogram")
parser.add_argument("-F", "--function", action="store_true",
    help="show a separate histogram per function")
parser.add_argument("-r", "--regexp", action="store_true",
    help="use regular expressions. Default is \"*\" wildcards only.")
parser.add_argument("-l", "--level", type=int,
    help="set the level of nested or recursive functions")
parser.add_argument("-v", "--verbose", action="store_true",
    help="print the BPF program (for debugging purposes)")
parser.add_argument("pattern",
    help="search expression for functions")
parser.add_argument("--ebpf", action="store_true",
    help=argparse.SUPPRESS)
args = parser.parse_args()
if args.duration and not args.interval:
    args.interval = args.duration
if not args.interval:
    args.interval = 99999999

def bail(error):
    print("Error: " + error)
    exit(1)

parts = args.pattern.split(':')
if len(parts) == 1:
    library = None
    pattern = args.pattern
elif len(parts) == 2:
    library = parts[0]
    libpath = BPF.find_library(library) or BPF.find_exe(library)
    if not libpath:
        bail("can't resolve library %s" % library)
    library = libpath
    pattern = parts[1]
else:
    bail("unrecognized pattern format '%s'" % args.pattern)

if not args.regexp:
    pattern = pattern.replace('*', '.*')
    pattern = '^' + pattern + '$'

# define BPF program
bpf_text = """
#include <uapi/linux/ptrace.h>

typedef struct ip_pid {
    u64 ip;
    u64 pid;
} ip_pid_t;

typedef struct prev_slot {
    u64 slot;
    u32 count;
} prev_slot_t;

typedef struct hist_key {
    ip_pid_t key;
    u64 slot;
} hist_key_t;

// 定义溢出事件结构体
struct overflow_event {
    ip_pid_t key;       // 函数标识
    prev_slot_t history; // 记录
};

TYPEDEF

BPF_ARRAY(avg, u64, 2);
STORAGE
FUNCTION

// BPF_HASH(history, ip_pid_t, call_history_t);
BPF_PERCPU_HASH(history, ip_pid_t, prev_slot_t);
// 发送 track 数据，使用 4MB 缓冲区
BPF_RINGBUF_OUTPUT(overflow, 1 << 12);

int trace_func_entry(struct pt_regs *ctx)
{
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u32 pid = pid_tgid;
    u32 tgid = pid_tgid >> 32;
    u64 ts = bpf_ktime_get_ns();

    FILTER
    ENTRYSTORE

    return 0;
}

int trace_func_return(struct pt_regs *ctx)
{
    u64 *tsp, delta;
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u32 pid = pid_tgid;
    u32 tgid = pid_tgid >> 32;

    // calculate delta time
    CALCULATE

    u32 lat = 0;
    u32 cnt = 1;
    avg.atomic_increment(lat, delta);
    avg.atomic_increment(cnt);

    FACTOR

    // store as histogram
    STORE

    return 0;
}
"""

# do we need to store the IP and pid for each invocation?
need_key = args.function or (library and not args.pid)

# code substitutions
if args.pid:
    bpf_text = bpf_text.replace('FILTER',
        'if (tgid != %d) { return 0; }' % args.pid)
else:
    bpf_text = bpf_text.replace('FILTER', '')
if args.milliseconds:
    bpf_text = bpf_text.replace('FACTOR', 'delta /= 1000000;')
    label = "msecs"
elif args.microseconds:
    bpf_text = bpf_text.replace('FACTOR', 'delta /= 1000;')
    label = "usecs"
else:
    bpf_text = bpf_text.replace('FACTOR', '')
    label = "nsecs"
if need_key:
    pid = '-1' if not library else 'tgid'

    if args.level and args.level > 1:
        bpf_text = bpf_text.replace('TYPEDEF',
            """
#define STACK_DEPTH %s

typedef struct {
    u64 ip;
    u64 start_ts;
} func_cache_t;

/* LIFO */
typedef struct {
    u32          head;
    func_cache_t cache[STACK_DEPTH];
} func_stack_t;
            """ % args.level)

        bpf_text = bpf_text.replace('STORAGE',
            """
BPF_HASH(func_stack, u32, func_stack_t);
BPF_HISTOGRAM(dist, hist_key_t);
            """)

        bpf_text = bpf_text.replace('FUNCTION',
            """
static inline int stack_pop(func_stack_t *stack, func_cache_t *cache) {
    if (stack->head <= 0) {
        return -1;
    }

    u32 index = --stack->head;
    if (index < STACK_DEPTH) {
        /* bound check */
        cache->ip       = stack->cache[index].ip;
        cache->start_ts = stack->cache[index].start_ts;
    }

    return 0;
}

static inline int stack_push(func_stack_t *stack, func_cache_t *cache) {
    u32 index = stack->head;

    if (index > STACK_DEPTH - 1) {
        /* bound check */
        return -1;
    }

    stack->head++;
    stack->cache[index].ip       = cache->ip;
    stack->cache[index].start_ts = cache->start_ts;

    return 0;
}
            """)

        bpf_text = bpf_text.replace('ENTRYSTORE',
            """
    u64 ip = PT_REGS_IP(ctx);
    func_cache_t cache = {
        .ip       = ip,
        .start_ts = ts,
    };

    func_stack_t *stack = func_stack.lookup(&pid);
    if (!stack) {
        func_stack_t new_stack = {
            .head = 0,
        };

        if (!stack_push(&new_stack, &cache)) {
            func_stack.update(&pid, &new_stack);
        }

        return 0;
    }

    if (!stack_push(stack, &cache)) {
        func_stack.update(&pid, stack);
    }
            """)

        bpf_text = bpf_text.replace('CALCULATE',
            """
    u64 ip, start_ts;
    func_stack_t *stack = func_stack.lookup(&pid);
    if (!stack) {
        /* miss start */
        return 0;
    }

    func_cache_t cache = {};
    if (stack_pop(stack, &cache)) {
        func_stack.delete(&pid);

        return 0;
    }
    ip       = cache.ip;
    start_ts = cache.start_ts;
    delta    = bpf_ktime_get_ns() - start_ts;
            """)

        bpf_text = bpf_text.replace('STORE',
            """
    hist_key_t key;
    key.key.ip  = ip;
    key.key.pid = %s;
    key.slot    = bpf_log2l(delta);
    dist.atomic_increment(key);

    if (stack->head == 0) {
        /* empty */
        func_stack.delete(&pid);
    }
            """ % pid)

    else:
        bpf_text = bpf_text.replace('STORAGE', 'BPF_HASH(ipaddr, u32);\n'\
            'BPF_HISTOGRAM(dist, hist_key_t);\n'\
            'BPF_HASH(start, u32);')
        # stash the IP on entry, as on return it's kretprobe_trampoline:
        bpf_text = bpf_text.replace('ENTRYSTORE',
            'u64 ip = PT_REGS_IP(ctx); ipaddr.update(&pid, &ip);'\
            ' start.update(&pid, &ts);')
        bpf_text = bpf_text.replace('STORE',
                """
    u64 ip, *ipp = ipaddr.lookup(&pid);
    if (ipp) {
        ip = *ipp;
        hist_key_t key;
        key.key.ip = ip;
        key.key.pid = %s;
        u64 slot = bpf_log2l(delta);
        key.slot = slot;
        dist.atomic_increment(key);
        ipaddr.delete(&pid);
        
        ip_pid_t func_key = { .ip = ip, .pid = %s };
        prev_slot_t *prev_slot = history.lookup(&func_key);
        prev_slot_t curr_slot = { .slot = slot, .count = 1 };
        
        if (prev_slot) {
            if (prev_slot->slot == slot) {                
                curr_slot = *prev_slot;
                curr_slot.count++;
            } else {
                struct overflow_event *evt = overflow.ringbuf_reserve(sizeof(struct overflow_event));
                if (evt) {
                    evt->key = func_key;
                    evt->history = *prev_slot;
                    overflow.ringbuf_submit(evt, 0);
                }
            }
        }
        
        history.update(&func_key, &curr_slot);
    }
                """ % (pid, pid))
else:
    bpf_text = bpf_text.replace('STORAGE', 'BPF_HISTOGRAM(dist);\n'\
                                           'BPF_HASH(start, u32);')
    bpf_text = bpf_text.replace('ENTRYSTORE', 'start.update(&pid, &ts);')
    bpf_text = bpf_text.replace('STORE',
        'dist.atomic_increment(bpf_log2l(delta));')

bpf_text = bpf_text.replace('TYPEDEF', '')
bpf_text = bpf_text.replace('FUNCTION', '')
bpf_text = bpf_text.replace('CALCULATE',
                """
    tsp = start.lookup(&pid);
    if (tsp == 0) {
        return 0;   // missed start
    }
    delta = bpf_ktime_get_ns() - *tsp;
    start.delete(&pid);
                """)

if args.verbose or args.ebpf:
    print(bpf_text)
    if args.ebpf:
        exit()

# load BPF program
b = BPF(text=bpf_text)

# attach probes
if not library:
    b.attach_kprobe(event_re=pattern, fn_name="trace_func_entry")
    b.attach_kretprobe(event_re=pattern, fn_name="trace_func_return")
    matched = b.num_open_kprobes()
else:
    b.attach_uprobe(name=library, sym_re=pattern, fn_name="trace_func_entry",
                    pid=args.pid or -1)
    b.attach_uretprobe(name=library, sym_re=pattern,
                       fn_name="trace_func_return", pid=args.pid or -1)
    matched = b.num_open_uprobes()

if matched == 0:
    print("0 functions matched by \"%s\". Exiting." % args.pattern)
    exit()

# header
print("Tracing %d functions for \"%s\"... Hit Ctrl-C to end." %
    (matched / 2, args.pattern))

# define prev_slot in C
class PrevSlot(ctypes.Structure):
    _fields_ = [
        ("slot", ctypes.c_uint64),
        ("count", ctypes.c_uint32),
    ]

# define overflow_event in C
class OverflowEvent(ctypes.Structure):
    _fields_ = [
        ("ip", ctypes.c_uint64),
        ("pid", ctypes.c_uint64),
        ("history", PrevSlot),
    ]
    
# define ip_pid in C
class IpPid(ctypes.Structure):
    _fields_ = [
        ("ip", ctypes.c_uint64),
        ("pid", ctypes.c_uint64)
    ]

# output
def get_section(key):
    if not library:
        return BPF.sym(key[0], -1)
    else:
        return "%s [%d]" % (BPF.sym(key[0], key[1]), key[1])

# See: https://github.com/iovisor/bcc/issues/2396
# Each cpu has a perf event ring buffer and a user thread to read the buffers.
# If there are burst of perf_submit() and user thread is not called to drain the ring buffer, some records may be lost.
# We should improve the performance of the timestamp tracking or change its behavior. 

def print_track_event(ip, pid, slot, count):
    low = (1 << slot) >> 1
    high = (1 << slot) - 1
    if (low == high):
        low -= 1
    print(f"F={get_section((ip, pid))},S:{low}->{high} {label},count:{count}")

# 处理 track 日志
def parse_track_event(ctx, data, size):
    event = ctypes.cast(data, ctypes.POINTER(OverflowEvent)).contents
    slot = event.history.slot
    count = event.history.count
    ip = event.ip
    pid = event.pid
    print_track_event(ip, pid, slot, count)

b["overflow"].open_ring_buffer(parse_track_event)

def print_last_history(b: BPF):
    history = b.get_table("history")
    for k, v in history.items():
        ip_pid = ctypes.cast(k, ctypes.POINTER(IpPid)).contents
        curr_slot = ctypes.cast(v, ctypes.POINTER(PrevSlot)).contents
        print_track_event(ip_pid.ip, ip_pid.pid, curr_slot.slot, curr_slot.count)

async def ring_buff_poll_loop(b: BPF):
    while True:
        try:
            b.ring_buffer_poll(timeout=1)
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            print_last_history(b)
            raise
        finally:
            print("ring buf poll done")

def hist_print(dist, total, counts):
    if need_key:
        dist.print_log2_hist(label, "Function", section_print_fn=get_section,
            bucket_fn=lambda k: (k.ip, k.pid))
    else:
        dist.print_log2_hist(label)

    if counts > 0:
        if label == 'msecs':
            total /= 1000000
        elif label == 'usecs':
            total /= 1000
        avg = total / counts
        print("\navg = %ld %s, total: %ld %s, count: %ld\n" %(avg, label, total, label, counts))

    dist.clear()
    b['avg'].clear()

async def hist_count(b: BPF):
    exiting = False if args.interval else True
    seconds = 0
    dist = b.get_table("dist")
    while True:
        try:
            await asyncio.sleep(args.interval)
            seconds += args.interval
            if args.duration and seconds >= args.duration:
                exiting = True
            
            total  = b['avg'][0].value
            counts = b['avg'][1].value
            hist_print(dist, total, counts)
            
            if exiting:
                print("Hist count Done")
                break
        except asyncio.CancelledError:
            total  = b['avg'][0].value
            counts = b['avg'][1].value
            hist_print(dist, total, counts)
            raise
        finally:
            print("hist count done")

async def main(b: BPF):
    # 启动两个独立协程
    hist_task = asyncio.create_task(hist_count(b))
    poll_task = asyncio.create_task(ring_buff_poll_loop(b))

    try:
        # 等待所有任务完成或被取消
        await asyncio.gather(hist_task, poll_task)
    except asyncio.CancelledError:
        print("all tasks done, cleaning up...")

def signal_handler():
    print("Received SIGINT, shutting down...")
    # See: https://docs.python.org/3/library/asyncio-task.html#asyncio.Task.cancel
    # Also see: https://stackoverflow.com/questions/40897428/please-explain-task-was-destroyed-but-it-is-pending-after-cancelling-tasks
    for task in asyncio.all_tasks(loop):
        task.cancel()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.run_until_complete(main(b))