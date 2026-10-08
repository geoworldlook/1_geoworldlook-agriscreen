#!/bin/sh
# Experiment C: run in order (c5/c6/c8 read out/c4_cv_series.csv written by c4).
cd "$(dirname "$0")"
for s in c0_baseline c1_layers_windows c1b_layer_loyo c3_s1_swi c3b_s1_samedates c4a_neighbours c4_fusion c5_events c6_event_diffs c7_floor c8_multcomp; do
  echo "== $s"; python3 $s.py 2>&1 | grep -v INFO
done
