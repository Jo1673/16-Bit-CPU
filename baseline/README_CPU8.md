# CPU8 — Small Synthesizable 8-bit CPU

CPU8 is intentionally small so it is easy to simulate, synthesize, and push through an RTL-to-GDS flow.

## Architecture

- 8-bit datapath
- 8 general-purpose 8-bit registers: R0-R7
- R0 is hard-wired to zero
- 8-bit program counter: 256 instruction addresses
- 16-bit fixed-width instructions
- 8-bit data-memory address space: 256 bytes
- Zero flag for conditional branches
- Harvard-style external instruction and data memory interfaces
- Synchronous active-low reset
- Single clock-edge execution model

The CPU core does not contain SRAM. The testbench models instruction and data memory externally. This keeps the synthesized core small and avoids depending on an SRAM macro during the first physical-design pass.

## Instruction Encoding

Bits [15:12] are the opcode.

For register-register instructions:
- rd = bits [11:9]
- rs = bits [8:6]

For immediate/address instructions:
- rd = bits [11:9] when used
- imm8/address = bits [7:0]

| Opcode | Mnemonic | Operation |
|---|---|---|
| 0x0 | NOP | No operation |
| 0x1 | LDI rd, imm8 | rd = imm8 |
| 0x2 | ADD rd, rs | rd = rd + rs |
| 0x3 | SUB rd, rs | rd = rd - rs |
| 0x4 | AND rd, rs | rd = rd & rs |
| 0x5 | OR rd, rs | rd = rd | rs |
| 0x6 | XOR rd, rs | rd = rd ^ rs |
| 0x7 | MOV rd, rs | rd = rs |
| 0x8 | LD rd, [addr] | rd = data_mem[addr] |
| 0x9 | ST rd, [addr] | data_mem[addr] = rd |
| 0xA | JMP addr | PC = addr |
| 0xB | JZ addr | jump when zero flag = 1 |
| 0xC | JNZ addr | jump when zero flag = 0 |
| 0xD | ADDI rd, imm8 | rd = rd + imm8 |
| 0xE | CMP rd, rs | zero flag = (rd == rs) |
| 0xF | HALT | stop execution |

## Run the RTL simulation

From the project root:

```bash
make sim
```

Expected final output includes:

```text
PASS: cpu8_core completed test program ...
MEM[20]=12 MEM[21]=13
```

Open waveforms with:

```bash
make wave
```

## Put the CPU into OpenROAD-flow-scripts

Assuming your OpenROAD-flow-scripts repository is at:

```text
~/OpenROAD-flow-scripts
```

From this project directory run:

```bash
cp -r orfs/designs/src/cpu8_core ~/OpenROAD-flow-scripts/flow/designs/src/
cp -r orfs/designs/sky130hd/cpu8_core ~/OpenROAD-flow-scripts/flow/designs/sky130hd/
```

Then:

```bash
cd ~/OpenROAD-flow-scripts/flow
util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu8_core/config.mk
```

If your Docker setup already drops you into the ORFS container instead, use the normal ORFS command inside the flow directory:

```bash
make DESIGN_CONFIG=designs/sky130hd/cpu8_core/config.mk
```

The supplied SDC uses a 50 ns clock period, or 20 MHz.

## Find physical-design outputs

After a successful flow:

```bash
find results/sky130hd/cpu8_core/base -maxdepth 1 -type f -printf '%f\n' | sort
find reports/sky130hd/cpu8_core/base -type f | sort
```

The final GDS is normally under:

```text
results/sky130hd/cpu8_core/base/
```

To open the final design in the ORFS GUI:

```bash
util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu8_core/config.mk gui_final
```

## Important tapeout distinction

Completing ORFS to GDS means you have completed RTL-to-GDS physical implementation of this core. A real foundry/shuttle tapeout generally needs additional top-level integration such as I/O pads, power pads, ESD structures, a pad ring or harness, signoff DRC/LVS, and the exact submission requirements of the selected shuttle/PDK.
