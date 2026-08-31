#!/bin/bash
# Run every face-labeling regression suite:  ./run_all.sh [path/to/Slicer]
set -u
SLICER="${1:-${SLICER:-/Applications/Slicer.app/Contents/MacOS/Slicer}}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_DIR="$(cd "$HERE/../../.." && pwd)"
total=0; failed=0
run() {
  out=$("$SLICER" --no-splash --no-main-window $2 --python-script "$HERE/$1" --exit-after-startup 2>&1)
  pass=$(echo "$out" | grep -cE '^  PASS'); fail=$(echo "$out" | grep -cE '^  FAIL')
  total=$((total+pass)); failed=$((failed+fail))
  printf "%-28s %3s pass  %s fail\n" "$1" "$pass" "$fail"
  [ "$fail" -gt 0 ] && echo "$out" | grep -E '^  FAIL'
}
for s in test_facelabels.py test_cellorder.py test_defect_holes.py; do run "$s" "--disable-modules"; done
for s in test_preprocess_labels.py test_legend_labels.py test_widget.py test_visible.py \
         test_warning.py test_apply_widget.py; do run "$s" "--additional-module-paths $MODULE_DIR"; done
run run_labeling_e2e.py ""
echo "-----"; echo "TOTAL: $total checks, $failed failures"
[ "$failed" -eq 0 ]
