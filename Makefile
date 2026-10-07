# Tool locations can be overridden: make test IVERILOG=/path/iverilog VVP=/path/vvp
PYTHON    ?= python3
YOSYS     ?= yosys
VERILATOR ?= verilator
IVERILOG  ?= iverilog
VVP       ?= vvp
export IVERILOG VERILATOR VVP

.PHONY: all test quick sim generate lint synth demo reset gate mutate clean
all: lint test reset gate

test sim:               ## full differential regression (RTL vs reference model)
	$(PYTHON) tools/verify.py
quick:
	$(PYTHON) tools/verify.py --quick
generate:
	$(PYTHON) tools/verify.py --generate-only
lint:
	$(VERILATOR) --lint-only --top-module cpu16_core -Wall rtl/cpu16_core.v rtl/cpu16_alu.v
reset:                  ## directed reset test
	mkdir -p build
	$(IVERILOG) -g2012 -s tb_reset -o build/tb_reset rtl/cpu16_core.v rtl/cpu16_alu.v tb/tb_reset.sv
	$(VVP) build/tb_reset
synth:                  ## generic Yosys synthesis; summary in build/synth_summary.txt
	mkdir -p build
	$(YOSYS) -q -l build/synth.log -p 'read_verilog rtl/cpu16_alu.v rtl/cpu16_core.v; synth -top cpu16_core; check -assert; tee -o build/synth_summary.txt stat; write_verilog -noattr build/cpu16_generic.v'
	@grep -E "Number of cells|_DFF|_SDFF" build/synth_summary.txt | tail -6
demo:
	mkdir -p build
	$(PYTHON) tools/asm16.py programs/demo.asm -o build/demo.hex --listing build/demo.lst
gate: synth            ## every program on the synthesized netlist, ports only
	$(PYTHON) tools/verify.py --netlist build/cpu16_generic.v
mutate:                 ## inject single-point RTL faults; every one must be caught
	$(PYTHON) tools/mutate.py
clean:
	rm -rf build
