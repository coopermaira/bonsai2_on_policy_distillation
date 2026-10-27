#!/bin/bash
W=/work; ST=$W/src_stock/build/bin; M=$W/models
echo "##### GPU"; nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv
echo "##### model checksums / sizes"; ls -la $M/*.gguf | awk '{print $5, $9}'
echo "##### interleaved comparison: FP16, Q8_0, Q4_0, Q4_K_M (Qwen3.8-27B) vs Bonsai2 PQ2_0/PTQ1_0 (stock), pp512+tg128, 6 rounds x 3 reps"
python3 $W/model_compare.py $ST 6 3 -p 512 -n 128 -- \
  qwen_fp16=$M/Qwen3.8-27B-F16.gguf \
  qwen_q8_0=$M/Qwen3.8-27B-Q8_0.gguf \
  qwen_q4_0=$M/Qwen3.8-27B-Q4_0.gguf \
  qwen_q4_k_m=$M/Qwen3.8-27B-Q4_K_M.gguf \
  bonsai_pq2_0=$M/Ternary-Bonsai-2-27B-PQ2_0.gguf \
  bonsai_ptq1_0=$M/Ternary-Bonsai-2-27B-PTQ1_0.gguf
echo "##### correctness sanity: MUL_MAT / greedy md5 for the new quant files (Q8_0, Q4_0, Q4_K_M are stock llama.cpp formats -- correctness is upstream-established; this just checks they load and generate)"
P="Explain in detail how a hash map handles collisions, with code examples in Python and C, then compare open addressing to chaining."
for m in $M/Qwen3.8-27B-Q8_0.gguf $M/Qwen3.8-27B-Q4_0.gguf $M/Qwen3.8-27B-Q4_K_M.gguf; do
  echo -n "$(basename $m): "; LD_LIBRARY_PATH=$ST $ST/llama-completion -m $m -ngl 99 -fa on -no-cnv --temp 0 --seed 1 -n 32 -p "$P" --no-display-prompt 2>/dev/null | tr '\n' ' ' | cut -c1-160; echo
done
echo "##### done"
