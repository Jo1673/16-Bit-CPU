#!/usr/bin/env python3
"""Self-checking CPU16 programs. Each builder returns (assembly_text, expected_memory).

expected_memory comes from ordinary Python arithmetic (math, sorted, bit operations, a CRC loop),
independent of both the RTL and tools/model16.py. verify.py requires the reference model's final
data memory to equal it, then requires the RTL to match the model instruction by instruction.
"""
import math
import random
from model16 import mem_init

M = 0xFFFF
def s16(x): return x - 0x10000 if x & 0x8000 else x

EDGES = [0, 1, 0x7FFF, 0x8000, 0x8001, 0xFFFF, 0x00FF]
COND_NAMES = ['BEQ', 'BNE', 'BHS', 'BLO', 'BMI', 'BPL', 'BVS', 'BVC',
              'BHI', 'BLS', 'BGE', 'BLT', 'BGT', 'BLE', 'BAL']

def flags_native(kind, a, b):
    """(N, Z, C, V) after CMP/SUB (a-b) or ADD (a+b), from plain integers."""
    if kind in ('CMP', 'SUB'):
        y, c = (a - b) & M, int(a >= b)
        v = int(not -32768 <= s16(a) - s16(b) <= 32767)
    else:
        y, c = (a + b) & M, int(a + b > M)
        v = int(not -32768 <= s16(a) + s16(b) <= 32767)
    return y >> 15, int(y == 0), c, v

def cond_native(name, kind, a, b):
    if kind == 'CMP' and name != 'BAL':        # compare conditions defined numerically, not via flags
        n, _, _, v = flags_native(kind, a, b)
        return {'BEQ': a == b, 'BNE': a != b, 'BHS': a >= b, 'BLO': a < b,
                'BMI': n == 1, 'BPL': n == 0, 'BVS': v == 1, 'BVC': v == 0,
                'BHI': a > b, 'BLS': a <= b, 'BGE': s16(a) >= s16(b), 'BLT': s16(a) < s16(b),
                'BGT': s16(a) > s16(b), 'BLE': s16(a) <= s16(b)}[name]
    n, z, c, v = flags_native(kind, a, b)
    return {'BEQ': z, 'BNE': not z, 'BHS': c, 'BLO': not c, 'BMI': n, 'BPL': not n,
            'BVS': v, 'BVC': not v, 'BHI': c and not z, 'BLS': (not c) or z,
            'BGE': n == v, 'BLT': n != v, 'BGT': (not z) and n == v, 'BLE': z or n != v,
            'BAL': True}[name]

def condition_tables(seed=1):
    rng = random.Random(seed)
    out, expected, slot, uid = [], {}, 0x9200, 0
    pairs = [(a, b) for a in EDGES for b in EDGES] + [(rng.randrange(65536), rng.randrange(65536)) for _ in range(6)]
    plan = [('CMP', a, b) for a, b in pairs] + [('ADD', *p) for p in pairs[::3]] + [('SUB', *p) for p in pairs[1::3]]
    for kind, a, b in plan:
        out += [f'LDI R1,{a}', f'LDI R2,{b}', 'LDI R3,0']
        mask = 0
        for k, name in enumerate(COND_NAMES):
            uid += 1
            out.append('CMP R1,R2' if kind == 'CMP' else f'MOV R4,R1')
            if kind != 'CMP':
                out.append(f'{kind} R4,R2')
            out += [f'{name} T{uid}', f'JMP N{uid}', f'T{uid}: LDI R5,{1 << k}', 'OR R3,R5', f'N{uid}:']
            if cond_native(name, kind, a, b):
                mask |= 1 << k
        out.append(f'ST R3,[{slot}]')
        expected[slot] = mask
        slot += 1
    out.append('HALT')
    return '\n'.join(out), expected

MUL = '''
mul:    LDI R3,0            ; R3:R4 = R1 * R2 (32-bit product), R1 and R2 destroyed
        LDI R4,0
        LDI R5,0
mloop:  CMP R2,R0
        BEQ mdone
        SHR R2
        BCC mskip
        ADD R4,R1
        ADC R3,R5
mskip:  SHL R1
        ADC R5,R5
        JMP mloop
mdone:  RET
'''

def multiply(seed=2):
    rng = random.Random(seed)
    pairs = [(0, 0), (1, 1), (0xFFFF, 0xFFFF), (0x8000, 2), (0x1234, 0xABCD), (255, 257)]
    pairs += [(rng.randrange(65536), rng.randrange(65536)) for _ in range(8)]
    out, exp = [], {}
    for i, (a, b) in enumerate(pairs):
        out += [f'LDI R1,{a}', f'LDI R2,{b}', 'CALL mul', f'ST R3,[{0x9000 + 2 * i}]', f'ST R4,[{0x9001 + 2 * i}]']
        exp[0x9000 + 2 * i], exp[0x9001 + 2 * i] = (a * b) >> 16, (a * b) & M
    return '\n'.join(out) + '\nHALT\n' + MUL, exp

def recursion():
    exp, out = {}, ['LDI R6,0xE000']
    for n in range(0, 9):
        out += [f'LDI R1,{n}', 'CALL fact', f'ST R2,[{0x9100 + n}]']
        exp[0x9100 + n] = math.factorial(n) & M
    fib = [0, 1]
    for _ in range(12): fib.append(fib[-1] + fib[-2])
    for n in range(0, 11):
        out += [f'LDI R1,{n}', 'CALL fib', f'ST R2,[{0x9120 + n}]']
        exp[0x9120 + n] = fib[n] & M
    out.append('HALT')
    out.append('''
fact:   CMP R1,R0
        BNE frec
        LDI R2,1
        RET
frec:   PUSH R7
        PUSH R1
        ADDI R1,-1
        CALL fact
        POP R1
        CALL mul
        MOV R2,R4
        POP R7
        RET
fib:    LDI R3,2
        CMP R1,R3
        BHS fibrec
        MOV R2,R1
        RET
fibrec: PUSH R7
        PUSH R1
        ADDI R1,-1
        CALL fib
        POP R1
        PUSH R2
        ADDI R1,-2
        CALL fib
        POP R3
        ADD R2,R3
        POP R7
        RET
''' + MUL)
    return '\n'.join(out), exp

def bubble_sort(signed, seed=3, n=12, base=0x9300):
    rng = random.Random(seed)
    data = [rng.choice([0, 0xFFFF, 0x8000, 0x7FFF, rng.randrange(65536)]) for _ in range(n)]
    out = []
    for i, d in enumerate(data):
        out += [f'LDI R1,{d}', f'ST R1,[{base + i}]']
    skip = 'BLE' if signed else 'BLS'
    out.append(f'''
        LDI R1,{base}
        LDI R2,{n - 1}
outer:  MOV R4,R1
        MOV R3,R2
inner:  LDX R5,[R4]
        MOV R6,R4
        ADDI R6,1
        LDX R7,[R6]
        CMP R5,R7
        {skip} noswap
        STX R7,[R4]
        STX R5,[R6]
noswap: ADDI R4,1
        ADDI R3,-1
        BNE inner
        ADDI R2,-1
        BNE outer
        HALT''')
    ordered = sorted(data, key=s16 if signed else None)
    return '\n'.join(out), {base + i: v for i, v in enumerate(ordered)}

def crc16(seed=4, n=24, base=0x9400, result=0x9420):
    rng = random.Random(seed)
    data = [rng.randrange(256) for _ in range(n)]
    out = []
    for i, d in enumerate(data):
        out += [f'LDI R1,{d}', f'ST R1,[{base + i}]']
    shifts = '\n'.join(['        SHL R4'] * 8)
    out.append(f'''
        LDI R1,0xFFFF
        LDI R2,{base}
        LDI R3,{n}
        LDI R7,0x1021
bytel:  LDX R4,[R2]
{shifts}
        XOR R1,R4
        LDI R5,8
bitl:   SHL R1
        BCC nopoly
        XOR R1,R7
nopoly: ADDI R5,-1
        BNE bitl
        ADDI R2,1
        ADDI R3,-1
        BNE bytel
        ST R1,[{result}]
        HALT''')
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & M if crc & 0x8000 else (crc << 1) & M
    return '\n'.join(out), {result: crc}

def wide_arithmetic(seed=5):
    """32-bit add/sub/shift/not/compare built from the 16-bit carry chain."""
    rng = random.Random(seed)
    vals = [0, 1, 0xFFFFFFFF, 0x80000000, 0x7FFFFFFF, 0x0000FFFF, 0xFFFF0000]
    pairs = [(rng.choice(vals), rng.choice(vals)) for _ in range(6)] + \
            [(rng.randrange(1 << 32), rng.randrange(1 << 32)) for _ in range(8)]
    out, exp, slot, uid = [], {}, 0x9500, 0
    def put(v):
        nonlocal slot
        out.extend([f'ST R5,[{slot}]', f'ST R6,[{slot + 1}]'])
        exp[slot], exp[slot + 1] = v >> 16, v & M
        slot += 2
    for a, b in pairs:
        ah, al, bh, bl = a >> 16, a & M, b >> 16, b & M
        out += [f'LDI R1,{ah}', f'LDI R2,{al}', f'LDI R3,{bh}', f'LDI R4,{bl}']
        out += ['MOV R5,R1', 'MOV R6,R2', 'ADD R6,R4', 'ADC R5,R3']; put((a + b) & 0xFFFFFFFF)
        out += ['MOV R5,R1', 'MOV R6,R2', 'SUB R6,R4', 'SBC R5,R3']; put((a - b) & 0xFFFFFFFF)
        out += ['MOV R5,R1', 'MOV R6,R2', 'SHL R6', 'ADC R5,R5']; put((a << 1) & 0xFFFFFFFF)
        out += ['MOV R5,R1', 'MOV R6,R2', 'SHR R5', 'RCR R6']; put(a >> 1)
        sa = a - (1 << 32) if a >> 31 else a
        sb = b - (1 << 32) if b >> 31 else b
        out += ['MOV R5,R1', 'MOV R6,R2', 'SAR R5', 'RCR R6']; put((sa >> 1) & 0xFFFFFFFF)
        out += ['NOT R5,R1', 'NOT R6,R2']; put(~a & 0xFFFFFFFF)
        uid += 1                                          # unsigned a >= b, then signed a < b
        out += ['LDI R6,1', 'MOV R5,R2', 'CMP R5,R4', 'MOV R5,R1', 'SBC R5,R3', f'BHS u{uid}', 'LDI R6,0', f'u{uid}:',
                f'ST R6,[{slot}]']
        exp[slot] = int(a >= b); slot += 1
        out += ['LDI R6,0', 'MOV R5,R2', 'CMP R5,R4', 'MOV R5,R1', 'SBC R5,R3', f'BGE s{uid}', 'LDI R6,1', f's{uid}:',
                f'ST R6,[{slot}]']
        exp[slot] = int(sa < sb); slot += 1
    out.append('HALT')
    return '\n'.join(out), exp

def shift_table():
    out, exp, slot = [], {}, 0x9700
    for a in EDGES + [0x4000, 0xAAAA, 0x5555]:
        for cin in (0, 1):
            for name in ('SHL', 'SHR', 'SAR', 'RCR'):
                out += ['LDI R5,1', 'CMP R0,R5' if cin == 0 else 'CMP R0,R0']   # 0<1 -> C=0 ; 0==0 -> C=1
                out += [f'LDI R1,{a}', f'{name} R1', 'LDI R2,0', 'ADC R2,R0', f'ST R1,[{slot}]', f'ST R2,[{slot + 1}]']
                if name == 'SHL': y, c = (a << 1) & M, a >> 15
                elif name == 'SHR': y, c = a >> 1, a & 1
                elif name == 'SAR': y, c = (a >> 1) | (a & 0x8000), a & 1
                else: y, c = (a >> 1) | (cin << 15), a & 1
                exp[slot], exp[slot + 1] = y, c
                slot += 2
    out.append('HALT')
    return '\n'.join(out), exp

def stack_and_copy(seed=7):
    rng = random.Random(seed)
    data = [rng.randrange(65536) for _ in range(10)]
    out = ['LDI R6,0xD000']
    for d in data: out += [f'LDI R1,{d}', 'PUSH R1']
    exp, base = {}, 0x9800
    for i in range(10):                                   # popping reverses the order
        out += ['POP R1', f'ST R1,[{base + i}]']
        exp[base + i] = data[9 - i]
    out += ['LDI R2,0x9800', 'LDI R4,0x9840', 'LDI R5,10',
            'cp: LDX R1,[R2]', 'STX R1,[R4]', 'ADDI R2,1', 'ADDI R4,1', 'ADDI R5,-1', 'BNE cp']
    for i in range(10): exp[0x9840 + i] = exp[base + i]
    out += ['ST R6,[0x9880]']; exp[0x9880] = 0xD000       # stack pointer restored
    out.append('HALT')
    return '\n'.join(out), exp

def directed():
    """Explicitly specified corner cases (docs/ISA.md). Each check stores a marker only if it passes."""
    exp = {0xA000: 0x00FF, 0xA001: 0x1111, 0xA002: mem_init(0x0200), 0xA003: 0x00AA, 0xA004: 0,
           0xA005: 1, 0xA006: 1, 0xA007: 1, 0xA008: 1, 0xA009: 1, 0xA00A: 1, 0xA00B: 1, 0xA00C: 1}
    src = '''
        LDI R6,0x0100
        LDI R1,0x1111
        PUSH R1,[R6]              ; pre-decrement: R6 = 0x00FF, mem[0x00FF] = 0x1111
        ST R6,[0xA000]
        LD R2,[0x00FF]
        ST R2,[0xA001]
        LDI R3,0x0200
        POP R3,[R3]               ; rd == rs: the loaded value wins over the increment
        ST R3,[0xA002]
        LDI R4,0x0300
        LDI R5,0x00AA
        STX R5,[R4]
        LD R4,[0x0300]
        ST R4,[0xA003]
        LDI R1,5
        CMP R1,R1                 ; Z=1 C=1
        LDI R2,0                  ; LDI changes Z,N only: C must stay 1
        LDI R7,0
        BHS cok
        LDI R7,0xBAD
cok:    ST R7,[0xA004]
        LDI R7,1
        LDI R1,0xFFFF
        ADDI R1,1                 ; R1=0, Z=1, C=1 (LDI above would clobber Z, so it comes first)
        BEQ zok
        LDI R7,0
zok:    BLO zbad                  ; C=1 so LO is not taken
        ST R7,[0xA005]
        BAL R5,after              ; link = address of the next instruction (label back)
back:   LDI R7,0
        ST R7,[0xA006]
        HALT
after:  LDI R4,back
        LDI R7,1
        CMP R4,R5
        BEQ linkok
        LDI R7,0
linkok: ST R7,[0xA006]
        BAL R0,skip1              ; link register R0: nothing is written
skip1:  LDI R7,1
        ST R7,[0xA007]
        LDI R1,1
        CMP R1,R1                 ; Z=1
        BNE never                 ; not taken: must still consume its extension word
        LDI R7,1
        ST R7,[0xA008]
        .word 0x000E              ; function 14: no such function, executes as NOP
        .word 0x003F              ; function 63: NOP
        .word 0x01C0              ; NOP with garbage in rd/rs
        .word 0x001F              ; BCC with cc=15 (reserved): never taken, consumes next word
        .word 0x0000
        LDI R7,1
        ST R7,[0xA009]
        LDI R1,tgt
        LDI R2,0
        JALR R2,R1                ; R2 = return address, jump to tgt
back2:  HALT
tgt:    LDI R4,back2
        LDI R7,1
        CMP R4,R2
        BEQ jalrok
        LDI R7,0
jalrok: ST R7,[0xA00A]
        LDI R1,tgt2
        JR R1
        HALT
tgt2:   LDI R7,1
        ST R7,[0xA00B]
        LDI R1,0x7FFF
        ADDI R1,1                 ; signed overflow: V=1, N=1
        BVC zbad                  ; V=1 so VC is not taken
        BLT zbad                  ; N == V so LT is not taken
        LDI R7,1
        ST R7,[0xA00C]
        HALT
zbad:   HALT
never:  HALT'''
    return src, exp

def library():
    return {'multiply': multiply(), 'recursion': recursion(),
            'sort_unsigned': bubble_sort(False), 'sort_signed': bubble_sort(True, seed=33),
            'crc16': crc16(), 'wide_arith': wide_arithmetic(), 'shifts': shift_table(),
            'stack_copy': stack_and_copy(), 'conditions': condition_tables(), 'directed': directed()}

if __name__ == '__main__':
    # Export the self-checking programs as readable .asm files:  python3 tools/progs.py programs
    import sys
    from pathlib import Path
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'programs')
    out.mkdir(exist_ok=True)
    notes = {'multiply': '32-bit product of two 16-bit values using shifts and ADC (CALL/RET).',
             'recursion': 'Recursive factorial and Fibonacci with PUSH/POP/CALL/RET and a software stack in R6.',
             'sort_unsigned': 'Bubble sort of 12 words with LDX/STX and an unsigned compare (BLS).',
             'sort_signed': 'Same sort with a signed compare (BLE).',
             'crc16': 'CRC-16/CCITT-FALSE over 24 bytes using shifts and the carry flag.',
             'wide_arith': '32-bit add, subtract, shift, NOT and compares built from ADC/SBC/RCR.',
             'shifts': 'Every shift/rotate for edge values and both carry-in states.',
             'stack_copy': 'PUSH/POP round trip and an LDX/STX memory copy.',
             'conditions': 'Every branch condition against CMP/ADD/SUB for edge-value pairs (large).',
             'directed': 'Corner cases: pointer ordering, flag preservation, link registers, reserved codes.'}
    for name, (asm, expected) in library().items():
        head = f'; {name}: {notes[name]}\n; Generated by tools/progs.py. Expected final data memory is computed there in plain Python.\n'
        if name == 'directed': name = 'corner_cases'
        (out / f'{name}.asm').write_text(head + asm.strip('\n') + '\n')
        print('wrote', out / f'{name}.asm')
