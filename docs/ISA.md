# CPU16 instruction set (v2)

## Architectural state

- Eight 16-bit registers R0–R7. R0 always reads zero and ignores writes (it has no storage).
- One 16-bit program counter (PC) counting instruction **words**.
- Flags: **Z** zero, **N** negative (bit 15), **C** carry, **V** signed overflow.
- One halted state.
- Synchronous active-low reset: PC = 0, R1–R7 = 0, Z = C = N = V = 0, halted = 0.
- Separate instruction and data address spaces, each 65,536 16-bit words.
- Arithmetic is modulo 65,536; signed values are two's complement.

R6 and R7 have no hardware meaning. The assembler and this document use **R6 as the stack
pointer** (`PUSH`/`POP` default to it) and **R7 as the link register** (`CALL`/`RET`).

## Instruction words

The opcode stays in bits [15:12] as in CPU8.

| Form | [15:12] | [11:9] | [8] | [7:6] | [5:0] |
|---|---|---|---|---|---|
| Register/register | opcode | rd | rs[2] | rs[1:0] | ignored (assemble as 0) |
| Short immediate/address | opcode | rd (or ignored) | 0 | imm8[7:6] | imm8[5:0] |
| Wide immediate/address | opcode | rd (or ignored) | 1 | ignored | ignored |
| Group 0 (opcode 0) | 0 | rd | rs[2] | rs[1:0] | function code |

In the wide form the **next whole 16-bit word is the operand**. Bit 8 selects the wide form
only for LDI, LD, ST, JMP, JZ, JNZ and ADDI; elsewhere it is part of the rs index.
Conditional branches (group 0, function `0x10..0x1F`) **always** have the extension word, taken
or not. Short immediates are zero-extended (0..255).

**Every 16-bit value is a defined instruction.** There are no illegal-instruction traps. Fields
marked "ignored" are ignored by hardware and the regression fills them with random bits to prove it.

## Flags

| Operation | Z, N | C | V |
|---|---|---|---|
| ADD, ADDI, ADC | result | carry out | signed overflow |
| SUB, CMP, SBC | result | **1 = no borrow** (unsigned a ≥ b) | signed overflow |
| AND, OR, XOR, MOV, NOT, LDI, LD, LDX, POP | result / loaded value | unchanged | unchanged |
| SHL SHR SAR RCR | result | bit shifted out | unchanged |
| ST, STX, PUSH, jumps, branches, NOP, HALT | unchanged | unchanged | unchanged |

Writes to R0 are discarded but flags still update (`LDI R0,7` leaves R0 = 0 and sets Z = 0).
Carry for subtraction follows the ARM convention, so `SUB` then `ADC`/`SBC` chains build
multi-word arithmetic: `ADD R6,R4` / `ADC R5,R3` adds 32-bit values; `SUB R6,R4` / `SBC R5,R3` subtracts.

## Opcodes

| Op | Assembly | Effect |
|---|---|---|
| 0 | group 0 | see next table |
| 1 | `LDI rd, imm` | rd = imm |
| 2 | `ADD rd, rs` | rd = rd + rs |
| 3 | `SUB rd, rs` | rd = rd − rs |
| 4 | `AND rd, rs` | rd = rd AND rs |
| 5 | `OR rd, rs` | rd = rd OR rs |
| 6 | `XOR rd, rs` | rd = rd XOR rs |
| 7 | `MOV rd, rs` | rd = rs |
| 8 | `LD rd, [addr]` | rd = data[addr] |
| 9 | `ST rd, [addr]` | data[addr] = rd |
| A | `JMP addr` | PC = addr |
| B | `JZ addr` | PC = addr if Z = 1 |
| C | `JNZ addr` | PC = addr if Z = 0 |
| D | `ADDI rd, imm` | rd = rd + imm (imm 0..255 short, or any 16-bit pattern wide, so `ADDI R1,-1` is wide) |
| E | `CMP rd, rs` | flags of rd − rs, no register write |
| F | `HALT` | stop; PC identifies the HALT word |

## Group 0 (opcode 0): function code in bits [5:0]

| Func | Assembly | Effect |
|---|---|---|
| 0x00 | `NOP` | nothing (rd, rs ignored) |
| 0x01 | `ADC rd, rs` | rd = rd + rs + C |
| 0x02 | `SBC rd, rs` | rd = rd − rs − (1 − C) |
| 0x03 | `NOT rd, rs` | rd = ~rs |
| 0x04 | `SHL rd` | logical shift left; C = old bit 15 (rs ignored) |
| 0x05 | `SHR rd` | logical shift right; C = old bit 0 |
| 0x06 | `SAR rd` | arithmetic shift right; C = old bit 0 |
| 0x07 | `RCR rd` | rotate right through carry: rd = {C, rd[15:1]}; C = old bit 0 |
| 0x08 | `LDX rd, [rs]` | rd = data[rs] |
| 0x09 | `STX rd, [rs]` | data[rs] = rd |
| 0x0A | `PUSH rd [, [rs]]` | rs = rs − 1; data[rs] = rd. Default rs = R6. If rd = rs the decremented value is stored |
| 0x0B | `POP rd [, [rs]]` | rd = data[rs]; rs = rs + 1. Default rs = R6. If rd = rs the loaded value wins |
| 0x0C | `JR rs` | PC = rs (rd ignored) |
| 0x0D | `JALR rd, rs` | rd = address of next instruction; PC = rs (no link if rd = R0) |
| 0x0E, 0x0F, 0x20–0x3F | — | reserved: execute as NOP (do not rely on this; they may be defined later) |
| 0x10–0x1F | `Bcc addr` | **two words**. If condition cc = func[3:0] holds: if rd ≠ R0 then rd = address after the extension word (link); PC = addr. rs ignored |

### Conditions (branch cc)

| cc | Mnemonic | Taken when | Meaning |
|---|---|---|---|
| 0 | `BEQ` | Z | equal |
| 1 | `BNE` | !Z | not equal |
| 2 | `BHS` / `BCS` | C | unsigned ≥ |
| 3 | `BLO` / `BCC` | !C | unsigned < |
| 4 | `BMI` | N | negative |
| 5 | `BPL` | !N | non-negative |
| 6 | `BVS` | V | overflow |
| 7 | `BVC` | !V | no overflow |
| 8 | `BHI` | C and !Z | unsigned > |
| 9 | `BLS` | !C or Z | unsigned ≤ |
| 10 | `BGE` | N = V | signed ≥ |
| 11 | `BLT` | N ≠ V | signed < |
| 12 | `BGT` | !Z and N = V | signed > |
| 13 | `BLE` | Z or N ≠ V | signed ≤ |
| 14 | `BAL` | always | branch always (with optional link) |
| 15 | — | never | reserved; consumes its extension word and falls through |

The compare-then-branch conditions are defined for the flags left by `CMP`/`SUB`. After other
instructions the flags are simply what the table above says they are.

## Assembly rules

- `Rn` are registers; `[addr]` and `[Rn]` are memory operands; `;` or `#` start comments.
- Numbers: decimal, `0x` hex, `0b` binary. Operands may be expressions without spaces:
  `label+2`, `0x10-1`, `.equ` names. Instruction names, register names and conditions are case-insensitive; labels are case-sensitive.
- Unsuffixed numeric operands 0..255 use the one-word form of LDI/LD/ST/JMP/JZ/JNZ/ADDI;
  other values use two words. `.W` forces two words, `.S` forces one and errors if the value exceeds 255.
  A **forward** label operand is always two words (so layout is known in one pass); a backward label under 256 is one word.
- Pseudo-instructions: `CALL addr` = `BAL R7, addr`; `RET` = `JR R7`; `JAL rd, addr` = `BAL rd, addr`.
  `BAL addr` jumps without linking. Only `BAL`/`JAL`/`CALL` accept a link register.
- Directives: `.org addr`, `.word value`, `.equ NAME value`.
- Duplicate labels, overlapping regions, invalid registers/values and an instruction crossing the end of the image are errors.

| Source | Machine word(s) |
|---|---|
| `LDI R1, 5` | `1205` |
| `LDI R1, 0x1234` | `1300 1234` |
| `ADDI R1, -1` | `D300 FFFF` |
| `ST R1, [0x8000]` | `9300 8000` |
| `ADC R1, R2` | `0281` |
| `SHL R3` | `0604` |
| `LDX R1, [R2]` | `0288` |
| `PUSH R7` / `POP R7` | `0F8A` / `0F8B` |
| `RET` | `01CC` |
| `BEQ label` | `0010 <label>` |
| `CALL label` | `0E1E <label>` |

## Calling convention used by the examples

`CALL f` puts the return address in R7. A function that calls others saves R7 first
(`PUSH R7` … `POP R7; RET`). R6 is the stack pointer and grows downward. Arguments and results travel
in R1–R5 as each program documents. `programs/recursion.asm` shows recursive factorial and Fibonacci.

## Execution timing (no wait states)

| Instruction | Cycles |
|---|---|
| One-word, no memory (ALU, shifts, JR, JALR, NOP, HALT, short JMP/JZ/JNZ, short LDI/ADDI) | 2 |
| Two-word, no memory (wide LDI/ADDI/JMP/JZ/JNZ, every Bcc) | 3 |
| One-word memory (LDX, STX, PUSH, POP) | 3 |
| Short `LD`/`ST` | 3 |
| Wide `LD`/`ST` | 4 |

Every unready fetch, extension fetch or data access adds a cycle. HALT stays halted until reset.
There is no overlap between instructions. These counts are checked cycle-exactly by the regression.
The internal PC advances during fetch; at a completed-instruction boundary it points to the next
instruction, the branch target, or the HALT word itself.

## Not provided

No interrupts, exceptions, privilege modes, cache, multiply/divide, barrel shifter, byte access, or
memory-mapped I/O in the core (I/O is whatever the system maps onto the data port). Programs
poll. A multiply routine is in `programs/multiply.asm`.

## Compatibility with CPU8

CPU8 opcodes and canonical short encodings are retained. Differences: 16-bit arithmetic and
addresses; word-addressed data; multicycle execution with valid/ready; CMP/ADD/SUB now also set
C, N and V (Z is unchanged); an old immediate word with the formerly ignored bit 8 set now selects
the wide form; opcode 0 words other than `0000` now decode as group-0 instructions.
The original CPU8 smoke program runs unchanged and is part of the regression.
