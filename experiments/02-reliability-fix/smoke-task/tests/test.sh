#!/bin/bash
mkdir -p /logs/verifier
if test "$(cat /app/reliability_probe.txt)" = ready; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
