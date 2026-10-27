#!/bin/bash
#SBATCH --job-name=install-harbor
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.out
#SBATCH --error=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.err
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
srun docker run --rm --network=host --cpus=8 --user "$(id -u):$(id -g)" -e HOME=/tmp -v /mnt/data/private/cmaira/bonsai_perf:/work ml_benchmark:latest bash -c '
set -e
pip install -q --user uv 2>&1 | tail -5
export PATH=/tmp/.local/bin:$PATH
uv tool install --quiet harbor-cli 2>&1 | tail -20 || pip install -q --user harbor-cli 2>&1 | tail -20
echo "=== harbor version/help check"
harbor --version 2>&1 || python3 -m harbor --version 2>&1 || echo "harbor CLI not on PATH yet, checking pip show"
pip show harbor-cli 2>&1 | head -5
echo "=== cloning terminal-bench task repo (for local task access)"
cd /work
rm -rf terminal-bench-tasks
git clone --depth 1 https://github.com/harbor-framework/terminal-bench-1 terminal-bench-tasks 2>&1 | tail -10
ls terminal-bench-tasks/tasks | wc -l
echo "=== docker available inside this container? (needed for task sandboxes)"
which docker || echo "NO DOCKER IN CONTAINER -- tasks need docker-in-docker or host docker socket"
'
