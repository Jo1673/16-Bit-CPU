#!/usr/bin/env python3
"""Two-pass CPU16 assembler. See docs/ISA.md for the instruction set.

Operands may be expressions without spaces: numbers, labels and .equ names joined by + or -
(e.g. table+2, 0x10-1). Label operands default to the wide (two-word) form.
"""
import argparse
from pathlib import Path
import re

OPS = {n: i for i, n in enumerate('NOP LDI ADD SUB AND OR XOR MOV LD ST JMP JZ JNZ ADDI CMP HALT'.split())}
RR = {'ADD', 'SUB', 'AND', 'OR', 'XOR', 'MOV', 'CMP'}          # op rd, rs
RI = {'LDI', 'LD', 'ST', 'ADDI'}                               # op rd, imm / [addr]
JUMP = {'JMP', 'JZ', 'JNZ'}                                    # op addr (short or wide)
G0_RR = {'ADC': 1, 'SBC': 2, 'NOT': 3}                         # opcode-0 functions: rd, rs
G0_R1 = {'SHL': 4, 'SHR': 5, 'SAR': 6, 'RCR': 7}               # rd only
G0_MEM = {'LDX': 8, 'STX': 9}                                  # rd, [rs]
G0_STK = {'PUSH': 10, 'POP': 11}                               # rd  or  rd, [rs]   (default rs = R6)
F_JR, F_JALR = 12, 13
CONDS = {'BEQ': 0, 'BNE': 1, 'BHS': 2, 'BCS': 2, 'BLO': 3, 'BCC': 3, 'BMI': 4, 'BPL': 5,
         'BVS': 6, 'BVC': 7, 'BHI': 8, 'BLS': 9, 'BGE': 10, 'BLT': 11, 'BGT': 12, 'BLE': 13,
         'BAL': 14}
SP, LR = 6, 7                                                  # software convention only
IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
TERM = re.compile(r'([+-]?)(0[xX][0-9a-fA-F_]+|0[bB][01_]+|[0-9]+|' + IDENT + ')')

def number(token):
    try:
        return int(token.replace('_', ''), 0)
    except ValueError:
        if re.fullmatch(r'-?[0-9]+', token):
            return int(token, 10)
        raise ValueError(f'not an integer: {token}')

def evaluate(expr, symbols, allow_unknown=False):
    """Sum of +/- terms. Returns (value, uses_a_symbol_not_yet_defined)."""
    pos, total, unknown, first = 0, 0, False, True
    while pos < len(expr):
        m = TERM.match(expr, pos)
        if not m or (not first and not m.group(1)):
            raise ValueError(f'bad expression: {expr}')
        sign = -1 if m.group(1) == '-' else 1
        text = m.group(2)
        if re.fullmatch(IDENT, text) and not re.match(r'0[xXbB]', text):
            if text in symbols:
                total += sign * symbols[text]
            elif allow_unknown:
                unknown = True
            else:
                raise ValueError(f'undefined symbol: {text}')
        else:
            total += sign * number(text)
        pos, first = m.end(), False
    if first:
        raise ValueError('empty expression')
    return total, unknown

def reg(token):
    if not re.fullmatch(r'[Rr][0-7]', token):
        raise ValueError(f'expected R0..R7, got {token}')
    return int(token[1])

def arity(base):
    if base in ('NOP', 'HALT', 'RET'): return (0,)
    if base in RR or base in G0_RR or base in G0_MEM or base in RI or base == 'JALR': return (2,)
    if base in G0_STK: return (1, 2)
    if base in G0_R1 or base in JUMP or base in ('JR', 'CALL'): return (1,)
    if base == 'JAL': return (2,)
    if base == 'BAL': return (1, 2)                    # BAL [link,] addr
    if base in CONDS: return (1,)
    raise ValueError(f'unknown instruction {base}')

def assemble(source):
    syms, records, pc = {}, [], 0
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = re.split(r'[;#]', raw, maxsplit=1)[0].strip()
        try:
            if ':' in line:
                label, line = line.split(':', 1)
                label = label.strip()
                if not re.fullmatch(IDENT, label) or label in syms:
                    raise ValueError('invalid or duplicate label')
                syms[label] = pc
                line = line.strip()
            if not line:
                continue
            fields = line.replace(',', ' ').replace('[', ' ').replace(']', ' ').split()
            mnemonic, args = fields[0].upper(), fields[1:]
            if mnemonic == '.ORG':
                if len(args) != 1:
                    raise ValueError('.org needs one numeric address')
                pc, _ = evaluate(args[0], syms)
                if not 0 <= pc <= 65535:
                    raise ValueError('.org out of range')
                continue
            if mnemonic == '.EQU':
                if len(args) != 2 or not re.fullmatch(IDENT, args[0]) or args[0] in syms:
                    raise ValueError('.equ NAME value (name must be new)')
                syms[args[0]], _ = evaluate(args[1], syms)
                continue
            base, _, suffix = mnemonic.partition('.')
            wide = False
            if mnemonic == '.WORD':
                if len(args) != 1:
                    raise ValueError('.word needs one value')
                size = 1
            else:
                if base not in OPS and base not in G0_RR and base not in G0_R1 and \
                        base not in G0_MEM and base not in G0_STK and base not in CONDS and \
                        base not in ('JR', 'JALR', 'JAL', 'CALL', 'RET'):
                    raise ValueError(f'unknown instruction {mnemonic}')
                if len(args) not in arity(base):
                    raise ValueError(f'{base} requires {" or ".join(map(str, arity(base)))} operands')
                if suffix not in ('', 'W', 'S') or (suffix and base not in RI | JUMP):
                    raise ValueError('width suffix only applies to immediate/address instructions')
                if base in RI | JUMP:
                    value, unknown = evaluate(args[-1], syms, allow_unknown=True)
                    wide = unknown or not 0 <= value <= 255
                    if suffix:
                        wide = suffix == 'W'
                elif base in CONDS or base in ('JAL', 'CALL'):
                    wide = True                        # conditional branches always have an extension word
                size = 2 if wide else 1
            if pc + size > 65536:
                raise ValueError('instruction crosses end of image; use .word for wrap test')
            records.append((lineno, pc, base, args, wide, mnemonic))
            pc += size
        except ValueError as exc:
            raise ValueError(f'line {lineno}: {exc}') from exc

    image, listing = {}, []
    def value(token, address=False):
        v, _ = evaluate(token, syms)
        if not (0 if address else -32768) <= v <= 65535:
            raise ValueError(f'value out of range: {token}')
        return v & 65535
    def g0(rd=0, rs=0, func=0):
        return (rd << 9) | (rs << 6) | func
    for lineno, pc, base, args, wide, mnemonic in records:
        try:
            if mnemonic == '.WORD':
                words = [value(args[0])]
            elif base in RR:
                words = [OPS[base] << 12 | reg(args[0]) << 9 | reg(args[1]) << 6]
            elif base in RI | JUMP:
                word = OPS[base] << 12
                if base in RI:
                    word |= reg(args[0]) << 9
                v = value(args[-1], base in ('LD', 'ST') or base in JUMP)
                if wide:
                    words = [word | 0x100, v]
                else:
                    if v > 255:
                        raise ValueError('short operand must be 0..255')
                    words = [word | v]
            elif base in ('NOP', 'HALT'):
                words = [OPS[base] << 12]
            elif base in G0_RR:
                words = [g0(reg(args[0]), reg(args[1]), G0_RR[base])]
            elif base in G0_R1:
                words = [g0(reg(args[0]), 0, G0_R1[base])]
            elif base in G0_MEM:
                words = [g0(reg(args[0]), reg(args[1]), G0_MEM[base])]
            elif base in G0_STK:
                words = [g0(reg(args[0]), reg(args[1]) if len(args) == 2 else SP, G0_STK[base])]
            elif base == 'JR':
                words = [g0(0, reg(args[0]), F_JR)]
            elif base == 'RET':
                words = [g0(0, LR, F_JR)]
            elif base == 'JALR':
                words = [g0(reg(args[0]), reg(args[1]), F_JALR)]
            elif base == 'CALL':
                words = [g0(LR, 0, 0x10 | CONDS['BAL']), value(args[0], True)]
            elif base == 'JAL':
                words = [g0(reg(args[0]), 0, 0x10 | CONDS['BAL']), value(args[1], True)]
            elif base in CONDS:
                link = reg(args[0]) if len(args) == 2 else 0
                if link and base != 'BAL':
                    raise ValueError('only BAL takes a link register')
                words = [g0(link, 0, 0x10 | CONDS[base]), value(args[-1], True)]
            else:
                raise ValueError(f'internal: unhandled {mnemonic}')
            for offset, word in enumerate(words):
                if pc + offset in image:
                    raise ValueError('overlapping .org regions')
                image[pc + offset] = word
            listing.append(f'{pc:04x}: ' + ' '.join(f'{w:04x}' for w in words) + f'  ; line {lineno}')
        except ValueError as exc:
            raise ValueError(f'line {lineno}: {exc}') from exc
    return image, '\n'.join(listing) + '\n'

def write_hex(image, path):
    lines, previous = [], -2
    for addr, word in sorted(image.items()):
        if addr != previous + 1:
            lines.append(f'@{addr:04x}')
        lines.append(f'{word:04x}')
        previous = addr
    Path(path).write_text('\n'.join(lines) + '\n')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('-o', '--output', type=Path, required=True)
    p.add_argument('--listing', type=Path)
    a = p.parse_args()
    try:
        img, listing = assemble(a.source.read_text())
        write_hex(img, a.output)
        if a.listing:
            a.listing.write_text(listing)
    except ValueError as exc:
        p.exit(1, f'{exc}\n')
