# Verification status — October 1, 2026 (CPU16 v2)

These results apply to the source identified in `SHA256SUMS`. No physical OpenROAD run was
performed: OpenROAD, an ORFS checkout with the Sky130 platform, and Docker were not available.

| Check | Result | Evidence |
|---|---|---|
| Assembler unit tests (encodings, expressions, 21 invalid-source cases) | Passed | `icarus.txt` |
| Reference model vs native Python results (multiply, recursion, sorts, CRC-16, 32-bit math, conditions, shifts, stack, corner cases) | Matched | `icarus.txt` |
| Instruction coverage (79 points: opcodes, function codes, every condition taken/not taken, short/wide forms) | Complete | `icarus.txt` |
| Icarus RTL differential simulation | 187 runs passed, 37,189 reference instructions per memory mode | `icarus.txt` |
| Verilator RTL differential simulation | Same 187 runs passed | `verilator.txt` |
| Verilator `-Wall` lint | Clean | `lint.txt` |
| Directed reset test | Passed | `reset.txt` |
| Yosys generic synthesis (`check -assert`, no latches) | Passed | `synthesis.txt` |
| Gate-level simulation, same 187 runs, ports only | Passed | `gate.txt` |
| Mutation analysis | 61 of 61 injected faults caught | `mutation.txt` |
| Installer/config path check | Not re-run in this delivery (config unchanged) | — |
| Sky130 technology mapping / P&R | Not run | Outstanding |
| STA / DRC / LVS / power | Not run | Outstanding |
| Harness / memory / boot integration | Not supplied | Requires selected target |

## What the 187 runs are

About 40 programs (10 algorithm programs, the original CPU8 smoke test, the demo, 14 random branchy
programs, 11 copies of programs with random bits in every ignored instruction field, 6 images of
65,536 random instruction words) times four memory behaviours, plus 15 runs with random mid-program resets.
Every instruction is checked against the reference model: PC, flags, R1–R7 (RTL only), and every fetch and
data transfer on the ports. With ready always high the cycle count of every instruction is checked exactly.
The gate-level run uses the same programs and port-level checks on the synthesized netlist.

## Synthesis (generic Yosys cells, not Sky130)

`synthesis.txt`: 2,131 generic cells including the ALU, 169 flip-flops. For comparison, the v1 delivery on
the same Yosys 0.33 measured 1,272 cells and 198 flip-flops: the new instructions cost about 70% more
logic, while removing R0's storage and `instruction_pc` removed 29 flip-flops. These are **not** Sky130 cell
counts, layout area, timing or power. The longest topological path is 43 generic gates; real timing needs STA after routing.

Yosys 0.33 is the version in Ubuntu 24.04. The earlier delivery's log came from Yosys 0.69; results differ
across versions, so use the numbers from your ORFS Yosys when planning.

## Tools used

- Icarus Verilog 12.0 (Ubuntu 24.04 package)
- Verilator 5.020 (Ubuntu 24.04 package)
- Yosys 0.33 (Ubuntu 24.04 package)
- Python 3.13 standard library only

## Reproduce

```bash
make lint && make test && make reset && make gate && make mutate
python3 tools/verify.py --sim verilator
```

The testbench clock is 10 ns for convenience. Zero-delay simulation does not establish an operating
frequency; the physical constraints target 50 ns (20 MHz) and must be checked after routing.
