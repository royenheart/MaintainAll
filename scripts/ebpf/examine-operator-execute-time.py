from bcc import BPF

# Load the eBPF program
bpf = BPF(text='''
#include <uapi/linux/ptrace.h>
#include <linux/bpf.h>

struct event {
    u64 start_ts;  // entry timestamp
    u64 end_ts;    // exit timestamp
    u64 duration;  // execution time
    u32 pid;       // process ID
};

// Hash map holding the start time of each in-flight call
BPF_HASH(start_times, u64, u64);
// Perf event array used to send results to user space
BPF_PERF_OUTPUT(events);

SEC("uprobe/func_entry")
int uprobe_entry(struct pt_regs *ctx) {
    u64 ts = bpf_ktime_get_ns();  // current timestamp (ns)
    u64 id = bpf_get_current_pid_tgid();  // pid_tgid of the current thread
    start_times.update(&id, &ts);  // record entry time
    return 0;
}

SEC("uretprobe/func_return")
int uretprobe_return(struct pt_regs *ctx) {
    u64 ts = bpf_ktime_get_ns();
    u64 id = bpf_get_current_pid_tgid();
    u64 *start_ts = start_times.lookup(&id);
    
    if (start_ts) {
        struct event e = {};
        e.start_ts = *start_ts;
        e.end_ts = ts;
        e.duration = ts - *start_ts;  // compute execution time
        e.pid = id >> 32;  // extract PID (tgid)
        events.perf_submit(ctx, &e, sizeof(e));  // emit to user space
        start_times.delete(&id);  // drop the entry
    }
    return 0;
}
''')

# Attach uprobe + uretprobe to the target function (here: redis-server's zslUpdateScore)
bpf.attach_uprobe(name="/home/hzxie/softwares/redis/6.2.9/bin/redis-server", sym="zslUpdateScore", fn_name="uprobe_entry")
bpf.attach_uretprobe(name="/home/hzxie/softwares/redis/6.2.9/bin/redis-server", sym="zslUpdateScore", fn_name="uretprobe_return")

# Callback that handles each event
def print_event(cpu, data, size):
    event = bpf["events"].event(data)
    print(f"PID: {event.pid}, Duration: {event.duration} ns")

# Bind the perf buffer to the callback
bpf["events"].open_perf_buffer(print_event)

# Poll for output forever
while True:
    try:
        bpf.perf_buffer_poll()
    except KeyboardInterrupt:
        exit()