export VLLM_LOGGING_LEVEL=DEBUG
export CUDA_LAUNCH_BLOCKING=1
export VLLM_TRACE_FUNCTION=1 
export NCCL_DEBUG=INFO
# 数据大小优化
## --cpu-offload-gb 40 每个 GPU offload 多少内存到 memory
## --gpu-memory-utilization 指定 GPU 最大内存使用量，默认 0.9（90%）
## --max-model-len 5000 指定模型上下文长度，可以减少一次性载入的数据量，deepseek 默认131072？
### ValueError: The model's max seq len (131072) is larger than the maximum number of tokens that can be stored in KV cache (89440). In tp2, pp2, offload 20G env.
vllm serve /mnt/deepseek --served-model-name deepseek70b --tensor-parallel-size 2 --pipeline-parallel-size 2 --cpu-offload-gb 20 --max-model-len 50000

# some previous examples
# OMP_NUM_THREADS=8 VLLM_CPU_OMP_THREADS_BIND="0-3|20-23" vllm serve /mnt/share/Qwen2.5-Coder-7B-Instruct/ --served-model-name qwen2.5Coder7BInstruct --host pink --port 8000 --tensor-parallel-size 2 --tokenizer /mnt/share/Qwen2.5-Coder-7B-Instruct/ --tokenizer-mode auto