# CPU16 (v2) — upgrade of Joaquin's CPU8

A small, custom 16-bit educational processor built from `cpu8_project.zip` (August 30, 2026).
The original RTL and smoke test are preserved in `baseline/`. It is not RISC-V or MIPS.

**Status:** RTL verified (differential simulation, gate-level simulation, mutation analysis),
generic synthesis checked, Sky130HD ORFS configuration prepared. Physical implementation and
foundry signoff are still outstanding. No GDS, area, timing, power, DRC or LVS result is claimed.

## What v2 changed

v1 could not express real programs: one flag, no shifts, no indirect addressing, no subroutines.
v2 keeps every CPU8 opcode and adds, inside opcode 0:

- flags **Z N C V**, `ADC`, `SBC`, `NOT`, `SHL SHR SAR RCR` (multi-word and signed arithmetic)
- 14 conditional branches (`BEQ BNE BHS BLO BHI BLS BGE BLT BGT BLE BMI BPL BVS BVC`)
- register-indirect `LDX`/`STX`, `PUSH`/`POP`, `CALL`/`RET` (`BAL` with link), `JR`, `JALR`
- assembler expressions and `.equ`

Verification was rebuilt so a wrong core cannot pass: independent reference model, programs whose
answers are computed in plain Python, random instruction soup, junk in ignored fields, four memory
behaviours, mid-run resets, cycle-exact timing, gate-level runs, and 61 injected faults that must all be caught.
Other fixes: R0 has no flip-flops, `instruction_pc` removed (HALT never advances PC), CMP reuses the
ALU subtractor, the Makefile honours tool paths, and the shipped diff and checksums match the RTL.

## Start here

1. `docs/ISA.md` to write programs, `docs/INTERFACE.md` to connect memories.
2. `docs/LEARNING_GUIDE.md` for the CPU8-to-CPU16 story (section 12 covers v2).
3. `docs/VERIFICATION.md` for what the tests prove; `verification/STATUS.md` for recorded results.
4. `docs/TAPEOUT.md` for ORFS and the remaining submission work.

## Run on Ubuntu / WSL

```bash
sudo apt update
sudo apt install -y make python3 iverilog verilator yosys
```

From the extracted `cpu16_upgrade` directory:

```bash
make lint      # Verilator -Wall on the RTL
make test      # full differential regression (Icarus if present, else Verilator)
make quick     # smaller matrix, ~10 s
make reset     # directed reset test
make gate      # synthesize, then run every program on the netlist (ports only)
make mutate    # inject 61 RTL faults; all must be caught (~2 min)
make demo      # assemble programs/demo.asm
```

Override tools with `make test IVERILOG=/path/iverilog VVP=/path/vvp VERILATOR=/path/verilator`
and `make synth YOSYS=/path/yosys`. `python3 tools/verify.py --sim verilator` forces Verilator.
Python uses only the standard library.

Assemble your own program:

```bash
python3 tools/asm16.py programs/demo.asm -o build/demo.hex --listing build/demo.lst
```

The demo stores `0x1336` at data address `0x8000`, counts down from 5 and stores `0xBEEF` at `0x8001`.
More programs are in `programs/` (recursion, multiply, sorts, CRC-16, 32-bit math, corner cases);
`python3 tools/progs.py programs` regenerates them. `.hex` files are simulation/loader input; they do not
become initialized ASIC SRAM by themselves.

## Build a core layout using your existing ORFS setup

```bash
bash install_into_orfs.sh "$HOME/OpenROAD-flow-scripts"
cd "$HOME/OpenROAD-flow-scripts/flow"
util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu16_core/config.mk
util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu16_core/config.mk gui_final
```

Inside an already running ORFS container use `make ...` without `util/docker_shell`. The installer copies
the single authoritative RTL in `rtl/`, backs up any earlier `cpu16_core` entries, and records the ORFS commit.

## What is included

| Path | Purpose |
|---|---|
| `rtl/cpu16_core.v`, `rtl/cpu16_alu.v` | The core: register file, decode, PC, controller, ALU |
| `tb/` | Differential testbench, reset test |
| `tools/asm16.py` | Assembler (labels, `.org`, `.word`, `.equ`, expressions, `.S`/`.W`) |
| `tools/model16.py` | Independent instruction-level reference model |
| `tools/progs.py` | Self-checking programs with expectations computed in Python |
| `tools/verify.py` | Generates programs/traces and runs the matrix |
| `tools/mutate.py` | Fault-injection check of the regression itself |
| `tools/collect_orfs.py` | Bundles physical-design evidence for review |
| `programs/` | Annotated example programs |
| `orfs/`, `install_into_orfs.sh` | Sky130HD configuration, timing budget, installer |
| `docs/` | ISA, interface contract, verification, tapeout steps, learning guide |
| `baseline/` | Unmodified original CPU8 source and test |
| `verification/` | Recorded logs and source hashes |

The core exposes separate external memory ports. It contains no SRAM, I/O pads, bootloader,
interrupts, caches, privilege modes or SoC. Data addresses refer to 16-bit words; each space holds
65,536 words (128 KiB). An instruction occupies one or two words.
