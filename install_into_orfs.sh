#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORFS_ROOT="${1:-$HOME/OpenROAD-flow-scripts}"
FLOW="$ORFS_ROOT/flow"
if [[ ! -f "$FLOW/Makefile" || ! -d "$FLOW/designs" ]]; then
  echo "Usage: bash install_into_orfs.sh /path/to/OpenROAD-flow-scripts" >&2
  echo "Missing ORFS flow at: $FLOW" >&2
  exit 1
fi
if [[ ! -f "$FLOW/platforms/sky130hd/config.mk" ]]; then
  echo "Missing sky130hd platform in this ORFS checkout." >&2
  exit 1
fi
SRC="$FLOW/designs/src/cpu16_core"
CFG="$FLOW/designs/sky130hd/cpu16_core"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
for DIR in "$SRC" "$CFG"; do
  if [[ -e "$DIR" ]]; then
    cp -a -- "$DIR" "${DIR}.backup-${STAMP}"
  fi
  mkdir -p -- "$DIR"
done
cp -- "$PROJECT/rtl/cpu16_core.v" "$PROJECT/rtl/cpu16_alu.v" "$SRC/"
cp -- "$PROJECT/orfs/config.mk" "$PROJECT/orfs/constraint.sdc" "$CFG/"
git -C "$ORFS_ROOT" rev-parse HEAD > "$CFG/orfs_commit.txt" 2>/dev/null || echo unknown > "$CFG/orfs_commit.txt"
echo "Installed CPU16 into: $FLOW"
echo "From that directory run:"
echo "  util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu16_core/config.mk"
echo "For the completed layout:"
echo "  util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu16_core/config.mk gui_final"
