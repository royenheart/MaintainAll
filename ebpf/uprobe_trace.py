# exeute means the <probe type:program path {cmd}>
# sudo bpftrace -e 'uprobe:/home/hzxie/gits/gpuprobe-daemon/data/uprobes/example:0x401127 { printf("Loop start at %d\n", nsecs); }'
# /home/hzxie/gits/gpuprobe-daemon/data/uprobes/example

# we can use objdump or gdb to get the address of our needed function and its all assemble codes
# objdump -d ./example | grep some_function
# addr2line -e ./example 0x401127
# or we can parse addr2line to read source codes

from bcc import BPF

bpf_code = """
int trace_loop_start(struct pt_regs *ctx) {
    u64 ts = bpf_ktime_get_ns();
    bpf_trace_printk("For loop start at: %llu\\n", ts);
    return 0;
}

int trace_loop_end(struct pt_regs *ctx) {
    u64 ts = bpf_ktime_get_ns();
    bpf_trace_printk("For loop end at: %llu\\n", ts);
    return 0;
}
"""

b = BPF(text=bpf_code)
# attach_uprobe sym means the function
# addr use the real address
b.attach_uprobe(name="/home/hzxie/gits/gpuprobe-daemon/data/uprobes/example", addr=0x401110, fn_name="trace_loop_start")
b.attach_uprobe(name="/home/hzxie/gits/gpuprobe-daemon/data/uprobes/example", addr=0x40113d, fn_name="trace_loop_end")

b.trace_print()