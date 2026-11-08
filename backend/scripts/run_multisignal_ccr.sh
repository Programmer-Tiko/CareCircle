#!/usr/bin/env bash
# Invoke through sbatch from backend/, after activating the project's Python env.
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo 'Usage: sbatch [your account/partition options] scripts/run_multisignal_ccr.sh manifest.csv [output-directory]'
  exit 2
fi
manifest="$1"
output_dir="${2:-data/out/multisignal-v1}"
# Avoid each numerical library spawning threads beyond the Slurm allocation.
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
python scripts/ccr_multisignal_ablation.py extract --manifest "$manifest" --output "$output_dir/features.csv" --perturbations
python scripts/ccr_multisignal_ablation.py evaluate --features "$output_dir/features.csv" --output "$output_dir/ablation.json" --permutations 100
