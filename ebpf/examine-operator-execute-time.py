from bcc import BPF

# 加载 eBPF 程序
bpf = BPF(text='''
#include <uapi/linux/ptrace.h>
#include <linux/bpf.h>

struct event {
    u64 start_ts;  // 入口时间戳
    u64 end_ts;    // 出口时间戳
    u64 duration;  // 执行时间
    u32 pid;       // 进程 ID
};

// 定义一个哈希表，用于存储每个函数调用的开始时间
BPF_HASH(start_times, u64, u64);
// 定义一个 perf 事件数组，用于输出结果到用户空间
BPF_PERF_OUTPUT(events);

SEC("uprobe/func_entry")
int uprobe_entry(struct pt_regs *ctx) {
    u64 ts = bpf_ktime_get_ns();  // 获取当前时间戳（纳秒）
    u64 id = bpf_get_current_pid_tgid();  // 获取线程 ID
    start_times.update(&id, &ts);  // 记录入口时间
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
        e.duration = ts - *start_ts;  // 计算执行时间
        e.pid = id >> 32;  // 提取 PID
        events.perf_submit(ctx, &e, sizeof(e));  // 输出到用户空间
        start_times.delete(&id);  // 清理记录
    }
    return 0;
}
''')

# 附加 uprobe 和 uretprobe（假设目标函数是 /usr/bin/myprog 的 my_function）
bpf.attach_uprobe(name="/home/hzxie/softwares/redis/6.2.9/bin/redis-server", sym="zslUpdateScore", fn_name="uprobe_entry")
bpf.attach_uretprobe(name="/home/hzxie/softwares/redis/6.2.9/bin/redis-server", sym="zslUpdateScore", fn_name="uretprobe_return")

# 定义回调函数来处理输出
def print_event(cpu, data, size):
    event = bpf["events"].event(data)
    print(f"PID: {event.pid}, Duration: {event.duration} ns")

# 绑定 perf 事件输出
bpf["events"].open_perf_buffer(print_event)

# 循环读取输出
while True:
    try:
        bpf.perf_buffer_poll()
    except KeyboardInterrupt:
        exit()