# How the CPU16 is verified

The aim is that a bug in the RTL cannot hide. Four layers, each independent of the others.

## 1. Reference model and native expectations (`tools/model16.py`, `tools/progs.py`)

`model16.py` executes one instruction per step with no state machine and no copy of the RTL's
adder: flags come from ordinary Python integers (unsigned and signed values). Every 16-bit word is a defined
instruction, so the model can run random memory.

`progs.py` builds real programs (multiply, recursion, sorts, CRC-16, 32-bit arithmetic, shift tables,
stack and copy, every branch condition over edge-value pairs, directed corner cases). Each also carries an
**expected final memory computed in plain Python** (`math.factorial`, `sorted`, a CRC loop, `//`).
`verify.py` requires the model to match those numbers before the RTL is run, so a bug common to the
model and RTL still shows up as a wrong sort or CRC.

Instruction coverage is asserted: all 16 opcodes, every function code, every branch condition taken and
not taken, short and wide forms of every wide-capable instruction (79 points).

## 2. Differential RTL simulation (`tb/tb_cpu16.sv`)

About 40 programs, each against four memory behaviours (`+MODE=0..3`, see `INTERFACE.md`):

- the 10 algorithm programs above, the original CPU8 smoke test and the demo
- 14 random branchy programs with every instruction type, forward branches, links and computed jumps
- the same programs again with **random garbage in every field the ISA calls ignored**
  (the model must behave identically first, then the RTL must too)
- 6 images of 65,536 **random instruction words** with HALT made rare
  (every possible encoding including reserved function codes is executed)
- scheduled mid-run resets (`+RESETS=n`): memory is restored, the program must restart at zero and match

Checks, black-box (ports only): every accepted instruction fetch and data transfer in order with
address/direction/data; exact per-instruction cycle counts when ready is always high; requests stable
while waiting; no X on outputs; no request while `rst_n` is low; nothing after HALT.
With `-DWHITEBOX` it also compares PC, flags and R1–R7 after every instruction.
`tb/tb_reset.sv` adds directed cancellation tests (stalled store, stalled fetch, stalled extension fetch, reset out of HALT).

## 3. Gate-level run

`make gate` synthesizes with Yosys and runs the **same testbench and programs** on the netlist
(`verify.py --netlist`), black-box. This is zero-delay simulation, not post-layout timing and not formal
equivalence.

## 4. Mutation testing (`tools/mutate.py`)

A regression that cannot fail proves nothing. `make mutate` injects 61 single faults (inverted
conditions, wrong flag updates, ignored ready, missing reset, wrong link address, ...) and requires each
to be caught. Add a mutant here whenever you add behaviour.

## What this does not prove

Not formal verification, not exhaustive, not physical. Timing, power, DRC, LVS, and integration
with the memories and harness remain outstanding (see `TAPEOUT.md`).

## Lessons recorded

While building this suite the testbench found a simulator-sensitivity bug in an early draft of the v2 register-file
read written as a function call inside a continuous assignment: Icarus did not re-evaluate it when a register
changed. The RTL now uses `always @*` read ports so every simulator agrees.
