# Install using ../install_into_orfs.sh before running ORFS.
export PLATFORM = sky130hd
export DESIGN_NAME = cpu16_core
export DESIGN_NICKNAME = cpu16_core

# Resolve relative to THIS config, not DESIGN_HOME or the caller's home.
CPU16_CFG_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
export VERILOG_FILES = $(CPU16_CFG_DIR)../../src/cpu16_core/cpu16_alu.v \
                       $(CPU16_CFG_DIR)../../src/cpu16_core/cpu16_core.v
export SDC_FILE = $(CPU16_CFG_DIR)constraint.sdc
export CLOCK_PERIOD = 50.0
export CORE_UTILIZATION = 35
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 5
export PLACE_DENSITY = 0.55
export TNS_END_PERCENT = 100
