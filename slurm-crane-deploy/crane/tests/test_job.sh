#!/bin/bash
#CBATCH --job-name=test_job
#CBATCH --output=test_job.out
#CBATCH --error=test_job.err
#CBATCH --time=00:05:00
#CBATCH --nodes=1
#CBATCH --ntasks=1

echo "Hello from Crane!"
echo "Alloc Job Nodes: $CRANE_JOB_NODELIST"
sleep 10
echo "Job completed!"