#!/usr/bin/env python3
"""Instruction-level CPU16 reference model (no FSM, no RTL-style adder structure).

Arithmetic flags come from plain Python integers (unsigned and signed values), not from the
ones'-complement adder used in the RTL, so the two are independent implementations.
Every 16-bit word is a defined instruction (see docs/ISA.md): there are no illegal opcodes.
"""
from dataclasses import dataclass, field

M = 0xFFFF
WIDE_OPS = (1, 8, 9, 10, 11, 12, 13)
# Row layout written to *.trace files and read by tb/tb_cpu16.sv:
#   pc z c n v halted r0..r7 | store_flag store_addr store_data | load_flag load_addr | cycles
ROW_FIELDS = 20

def mem_init(addr):
    """Power-up contents of every data-memory word in all tests (deliberately not zero)."""
    return (addr * 0x9E37 + 0x3039) & M

def s16(x):
    return x - 0x10000 if x & 0x8000 else x

def has_extension(word):
    op = word >> 12
    return bool((op in WIDE_OPS and word & 0x100) or (op == 0 and (word >> 4) & 3 == 1))

def cond_true(cc, z, c, n, v):
    return bool({0: z, 1: not z, 2: c, 3: not c, 4: n, 5: not n, 6: v, 7: not v,
                 8: c and not z, 9: (not c) or z, 10: n == v, 11: n != v,
                 12: (not z) and n == v, 13: z or n != v, 14: True, 15: False}[cc])

@dataclass
class CPU:
    image: dict
    pc: int = 0
    r: list = field(default_factory=lambda: [0] * 8)
    z: int = 0
    c: int = 0
    n: int = 0
    v: int = 0
    halted: int = 0
    memory: dict = field(default_factory=dict)
    coverage: set = field(default_factory=set)
    first: dict = field(default_factory=dict)         # address -> first word of every executed instruction

    def load(self, addr):
        return self.memory.get(addr & M, mem_init(addr & M))

    def set_zn(self, value):
        self.z, self.n = int(value == 0), value >> 15

    def step(self):
        start = self.pc
        word = self.image.get(start, 0)
        self.first[start] = word
        self.pc = (start + 1) & M
        op, rd, rs, func = word >> 12, (word >> 9) & 7, (word >> 6) & 7, word & 63
        imm, cycles = word & 255, 2
        if has_extension(word):
            imm = self.image.get(self.pc, 0)
            self.pc = (self.pc + 1) & M
            cycles += 1
        a, b = self.r[rd], self.r[rs]
        write, wvalue = False, 0
        store, load = (0, 0, 0), (0, 0)
        cov = self.coverage
        cov.add(('op', op))
        if op in WIDE_OPS:
            cov.add(('form', op, bool(word & 0x100)))
        if op == 0:
            cov.add(('fn', 'bcc' if func >> 4 == 1 else ('nop' if func == 0 or func > 13 else func)))
            if func >> 4 == 1:
                cc = func & 15
                taken = cond_true(cc, self.z, self.c, self.n, self.v)
                cov.add(('cc', cc, taken))
                if taken:
                    if rd: self.r[rd] = self.pc
                    self.pc = imm
            elif func == 1:                               # ADC
                total = a + b + self.c
                self.v = int(not -32768 <= s16(a) + s16(b) + self.c <= 32767)
                self.c = int(total > M)
                write, wvalue = True, total & M
                self.set_zn(wvalue)
            elif func == 2:                               # SBC
                borrow = 1 - self.c
                self.v = int(not -32768 <= s16(a) - s16(b) - borrow <= 32767)
                self.c = int(a >= b + borrow)
                write, wvalue = True, (a - b - borrow) & M
                self.set_zn(wvalue)
            elif func == 3:                               # NOT rd, ~rs
                write, wvalue = True, ~b & M
                self.set_zn(wvalue)
            elif func in (4, 5, 6, 7):                    # SHL SHR SAR RCR (rs ignored)
                if func == 4: y, self.c = (a << 1) & M, a >> 15
                elif func == 5: y, self.c = a >> 1, a & 1
                elif func == 6: y, self.c = (a >> 1) | (a & 0x8000), a & 1
                else: y, self.c = (a >> 1) | (self.c << 15), a & 1
                write, wvalue = True, y
                self.set_zn(y)
            elif func in (8, 9, 10, 11):                  # LDX STX PUSH POP
                cycles += 1
                if func == 10:                            # pre-decrement pointer
                    ptr = (b - 1) & M
                    if rs: self.r[rs] = ptr
                elif func == 11:                          # post-increment pointer
                    ptr = b
                    if rs: self.r[rs] = (b + 1) & M
                else:
                    ptr = b
                if func in (9, 10):                       # store: rd is read after the pointer update
                    data = self.r[rd]
                    self.memory[ptr] = data
                    store = (1, ptr, data)
                else:                                     # load: the loaded value wins if rd == rs
                    y = self.load(ptr)
                    load = (1, ptr)
                    self.set_zn(y)
                    if rd: self.r[rd] = y
            elif func == 12:                              # JR rs
                self.pc = b
            elif func == 13:                              # JALR rd, rs
                if rd: self.r[rd] = self.pc
                self.pc = b
            # function 0 and every unlisted function code: NOP
        elif op == 1:
            write, wvalue = True, imm
            self.set_zn(imm)
        elif op in (2, 13):                               # ADD ADDI
            operand = b if op == 2 else imm
            total = a + operand
            self.c = int(total > M)
            self.v = int(not -32768 <= s16(a) + s16(operand) <= 32767)
            write, wvalue = True, total & M
            self.set_zn(wvalue)
        elif op in (3, 14):                               # SUB CMP
            self.c = int(a >= b)
            self.v = int(not -32768 <= s16(a) - s16(b) <= 32767)
            y = (a - b) & M
            self.set_zn(y)
            if op == 3:
                write, wvalue = True, y
        elif op in (4, 5, 6, 7):
            y = {4: a & b, 5: a | b, 6: a ^ b, 7: b}[op]
            write, wvalue = True, y
            self.set_zn(y)
        elif op == 8:
            cycles += 1
            y = self.load(imm)
            load = (1, imm)
            write, wvalue = True, y
            self.set_zn(y)
        elif op == 9:
            cycles += 1
            self.memory[imm] = a
            store = (1, imm, a)
        elif op == 10:
            self.pc = imm
        elif op == 11:
            cov.add(('jz', bool(self.z)))
            if self.z: self.pc = imm
        elif op == 12:
            cov.add(('jnz', not self.z))
            if not self.z: self.pc = imm
        elif op == 15:
            self.halted, self.pc = 1, start
        if write and rd:
            self.r[rd] = wvalue
        self.r[0] = 0
        return [self.pc, self.z, self.c, self.n, self.v, self.halted, *self.r, *store, *load, cycles]

def trace(image, limit=30000, stop_at_halt=True):
    """Run until HALT (or exactly `limit` instructions if stop_at_halt is False)."""
    cpu, rows = CPU(image), []
    for _ in range(limit):
        rows.append(cpu.step())
        if cpu.halted and stop_at_halt:
            return rows, cpu
    if stop_at_halt:
        raise RuntimeError('reference did not halt before instruction limit')
    return rows, cpu
