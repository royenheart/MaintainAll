#!/bin/bash
#SBATCH --job-name=test_job
#SBATCH --output=test_job.out
#SBATCH --error=test_job.err
#SBATCH --time=00:05:00
#SBATCH --nodes=1
#SBATCH --ntasks=1

echo "Hello from Slurm!"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_NODELIST"
echo "CPUs: $SLURM_CPUS_PER_TASK"
sleep 10
echo "Job completed!"