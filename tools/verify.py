#!/usr/bin/env python3
"""Generate programs and reference traces, then run the RTL (or a netlist) against them.

  python3 tools/verify.py                  full RTL regression (Icarus if present, else Verilator)
  python3 tools/verify.py --sim verilator  force a simulator
  python3 tools/verify.py --quick          smaller matrix (used by mutation testing)
  python3 tools/verify.py --netlist build/cpu16_generic.v   black-box run on a synthesized netlist
  python3 tools/verify.py --generate-only  unit tests, model self-checks and coverage only
"""
import argparse
import concurrent.futures as cf
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm16 import assemble, write_hex
from model16 import trace, CPU, ROW_FIELDS
import progs

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
MODES = (0, 1, 2, 3)

# ------------------------------------------------------------------ assembler unit tests
class AssemblerChecks(unittest.TestCase):
    def test_known_encodings(self):
        image, _ = assemble('LDI R1,5\nADD R1,R2\nLDI.W R3,0x1234\nADDI R4,-1\nHALT')
        self.assertEqual(list(image.values()), [0x1205, 0x2280, 0x1700, 0x1234, 0xd900, 0xffff, 0xf000])
    def test_extended_encodings(self):
        pick = lambda text: list(assemble(text)[0].values())
        self.assertEqual(pick('ADC R1,R2'), [0x0281])
        self.assertEqual(pick('SHL R3'), [0x0604])
        self.assertEqual(pick('LDX R1,[R2]'), [0x0288])
        self.assertEqual(pick('PUSH R7'), [0x0f8a])
        self.assertEqual(pick('POP R7'), [0x0f8b])
        self.assertEqual(pick('RET'), [0x01cc])
        self.assertEqual(pick('x: BEQ x'), [0x0010, 0x0000])
        self.assertEqual(pick('x: BAL R5,x'), [0x0a1e, 0x0000])
        self.assertEqual(pick('x: CALL x'), [0x0e1e, 0x0000])
        self.assertEqual(pick('x: BLT x'), [0x001b, 0x0000])
    def test_labels_and_expressions(self):
        image, _ = assemble('JMP end\nNOP\nend: HALT')
        self.assertEqual(image, {0: 0xa100, 1: 3, 2: 0, 3: 0xf000})
        image, _ = assemble('.equ K 0x10\nLDI R1,K+1\nLD R2,[K-1]\nLDI.W R3,-2+K')
        self.assertEqual(list(image.values()), [0x1211, 0x840f, 0x1700, 0x000e][:len(image)])
    def test_rejections(self):
        for text in ('LDI R8,1', 'LDI.S R1,256', 'LDI R1,65536', 'JMP -1', 'NOP.W', 'ADD R1', 'HALT 1',
                     'LDI R1,missing', 'x:NOP\nx:HALT', '.org 0\nNOP\n.org 0\nHALT', '.org 65535\nLDI.W R1,1',
                     'SHL R1,R2', 'BEQ.W x\nx:NOP', 'PUSH R9', 'RET R1', 'JR', 'BEQ R1,x\nx:NOP', 'LDX R1,R2,R3',
                     '.equ A 1\n.equ A 2', 'LDI R1,1+', 'LDI R1,2 3'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                assemble(text)

# ------------------------------------------------------------------ program generation
def junkify(image, cpu, rng):
    """Fill every field the ISA declares ignored with random bits; behaviour must not change."""
    out = dict(image)
    for addr, w in cpu.first.items():
        op, func = w >> 12, w & 63
        if op == 0:
            if func >> 4 == 1: w |= rng.randrange(8) << 6                   # BCC: rs ignored
            elif func in (4, 5, 6, 7): w |= rng.randrange(8) << 6          # shifts: rs ignored
            elif func == 12: w |= rng.randrange(8) << 9                    # JR: rd ignored
            elif func == 0 or func > 13: w |= rng.randrange(64) << 6       # NOP-like: rd/rs ignored
        elif op in (1, 8, 9, 13):
            if w & 0x100: w |= rng.randrange(256)                          # wide form: [7:0] ignored
        elif op in (10, 11, 12):
            w |= rng.randrange(8) << 9                                     # jumps: rd ignored
            if w & 0x100: w |= rng.randrange(256)
        elif op in (2, 3, 4, 5, 6, 7, 14):
            w |= rng.randrange(64)                                         # reg/reg: [5:0] ignored
        elif op == 15:
            w |= rng.randrange(4096)
        out[addr] = w
    return out

def branchy(seed, n=160):
    """Random straight-line-plus-forward-branch program covering every instruction type."""
    rng = random.Random(1000 + seed)
    imm = lambda: rng.choice([0, 1, 2, 255, 256, 0x7FFF, 0x8000, 0xFFFF, rng.randrange(65536), rng.randrange(256)])
    addr = lambda: rng.choice([0, 1, 255, 256, 0x7FFF, 0x8000, 0xFFFF, rng.randrange(65536)])
    R = lambda: f'R{rng.randrange(8)}'
    L = [f'LDI R{i},{imm()}' for i in range(1, 8)]
    conds = list(progs.COND_NAMES) + ['BCS', 'BCC']
    for k in range(n):
        L.append(f'L{k}:')
        tgt = f'L{min(n, k + 1 + (rng.randrange(6) if rng.random() < 0.8 else rng.randrange(60)))}'
        r = rng.random()
        if r < 0.10: L.append(f'{rng.choice(conds)} {tgt}')
        elif r < 0.14: L.append(f'{rng.choice(["JMP", "JZ", "JNZ"])} {tgt}')
        elif r < 0.17: L.append(f'BAL {R()},{tgt}')
        elif r < 0.19: L.append(f'CALL {tgt}')
        elif r < 0.21:
            reg = rng.choice(['R1', 'R2', 'R3', 'R4', 'R5'])
            L += [f'LDI {reg},{tgt}', rng.choice([f'JR {reg}', f'JALR {R()},{reg}'])]
        elif r < 0.25: L.append(f'{rng.choice(["SHL", "SHR", "SAR", "RCR"])} {R()}')
        elif r < 0.30: L.append(f'{rng.choice(["ADC", "SBC", "NOT"])} {R()},{R()}')
        elif r < 0.34: L.append(f'{rng.choice(["LDX", "STX"])} {R()},[{R()}]')
        elif r < 0.38: L.append(f'{rng.choice(["PUSH", "POP"])} {R()},[{R()}]')
        elif r < 0.44: L.append(f'{rng.choice(["LD", "ST"])} {R()},[{addr()}]')
        elif r < 0.47: L.append('NOP')
        elif r < 0.55: L.append(f'{rng.choice(["LDI", "ADDI"])}{rng.choice(["", "", ".W"])} {R()},{imm()}')
        else: L.append(f'{rng.choice(["ADD", "SUB", "AND", "OR", "XOR", "MOV", "CMP"])} {R()},{R()}')
    L += [f'L{n}:', 'HALT']
    return '\n'.join(L)

def fuzz_image(seed):
    """All 65,536 words random (HALT made rare); program counter wanders through random code."""
    rng = random.Random(7000 + seed)
    while True:
        image = {}
        for a in range(65536):
            w = rng.randrange(65536)
            if w >> 12 == 15 and rng.random() > 1 / 40: w = (w & 0x0FFF) | (rng.randrange(15) << 12)
            image[a] = w
        try:
            rows, cpu = trace(image, limit=4000)
            if 300 <= len(rows) <= 4000: return image, rows, cpu
        except RuntimeError:
            pass
        rng.seed(rng.random())

def build_cases(quick=False):
    """name -> image dict. Also returns coverage and writes hex/trace files to build/."""
    BUILD.mkdir(exist_ok=True)
    images = {}
    old = [0x1205, 0x1407, 0x2280, 0x9220, 0x160c, 0xe2c0, 0xb008, 0x18ee, 0x8a20, 0xda01, 0x9a21, 0xf000]
    images['cpu8_original_smoke'] = dict(enumerate(old))
    images['demo'] = assemble((ROOT / 'programs/demo.asm').read_text())[0]
    sources = {}
    for name, (asm, exp) in progs.library().items():
        sources[name] = (asm, exp)
    for seed in range(6 if quick else 14):
        sources[f'branchy_{seed}'] = (branchy(seed), None)
    return images, sources

def model_check_and_write(name, image, expected=None):
    rows, cpu = trace(image, limit=60000)
    if expected is not None:
        bad = [hex(a) for a, v in expected.items() if cpu.memory.get(a) != v]
        if bad:
            raise SystemExit(f'reference model disagrees with native Python results in {name}: {bad[:5]}')
    write_hex(image, BUILD / f'{name}.hex')
    (BUILD / f'{name}.trace').write_text(''.join(' '.join(f'{v:04x}' for v in r) + '\n' for r in rows))
    return rows, cpu

def required_coverage():
    need = {('op', o) for o in range(16)}
    need |= {('fn', f) for f in range(1, 14)} | {('fn', 'nop'), ('fn', 'bcc')}
    for cc in range(16):
        if cc < 14: need |= {('cc', cc, True), ('cc', cc, False)}
        else: need.add(('cc', cc, cc == 14))
    need |= {('jz', True), ('jz', False), ('jnz', True), ('jnz', False)}
    need |= {('form', o, w) for o in (1, 8, 9, 10, 11, 12, 13) for w in (False, True)}
    return need

# ------------------------------------------------------------------ simulation
def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], cwd=ROOT, **kwargs)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sim', choices=['auto', 'iverilog', 'verilator'], default='auto')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--generate-only', action='store_true')
    ap.add_argument('--netlist', type=Path, help='run black-box on this synthesized netlist (Icarus only)')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 1)
    ap.add_argument('--rtl', type=Path, default=Path('rtl'), help='directory holding cpu16_core.v / cpu16_alu.v')
    ap.add_argument('--fail-fast', action='store_true', help='stop at the first failing run')
    ap.add_argument('--reuse', action='store_true', help='reuse programs/traces already in build/ (mutation testing)')
    args = ap.parse_args()

    result = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(AssemblerChecks))
    if not result.wasSuccessful():
        return 1

    lengths = {}
    if args.reuse:
        for line in (BUILD / 'cases.txt').read_text().split('\n'):
            if line.strip():
                n, r = line.split()
                lengths[n] = int(r)
        total = sum(lengths.values())
    else:
        images, sources = build_cases(args.quick)
        coverage, traces, rng = set(), {}, random.Random(99)
        for name, image in images.items():
            traces[name] = model_check_and_write(name, image)
        for name, (asm, exp) in sources.items():
            image = assemble(asm)[0]
            images[name] = image
            traces[name] = model_check_and_write(name, image, exp)
        # same programs with random garbage in every ignored field must behave identically
        for name in ['cpu8_original_smoke', 'demo', 'directed', 'recursion', 'wide_arith', 'conditions',
                     'branchy_0', 'branchy_1', 'branchy_2', 'shifts', 'stack_copy'][: 5 if args.quick else None]:
            rows, cpu = traces[name]
            junk = junkify(images[name], cpu, rng)
            jrows, _ = trace(junk, limit=60000)
            if jrows != rows:
                raise SystemExit(f'model changed behaviour when ignored fields were filled in {name}')
            images[f'junk_{name}'] = junk
            traces[f'junk_{name}'] = model_check_and_write(f'junk_{name}', junk)
        for seed in range(2 if args.quick else 6):
            image, rows, cpu = fuzz_image(seed)
            images[f'fuzz_{seed}'] = image
            traces[f'fuzz_{seed}'] = model_check_and_write(f'fuzz_{seed}', image)
        for rows, cpu in traces.values():
            coverage |= cpu.coverage
        missing = sorted(map(str, required_coverage() - coverage))
        if missing:
            raise SystemExit('instruction coverage holes: ' + ', '.join(missing))
        total = sum(len(r) for r, _ in traces.values())
        print(f'Generated {len(images)} programs, {total} reference instructions; instruction coverage complete '
              f'({len(required_coverage())} points).')
        lengths = {n: len(r) for n, (r, _) in traces.items()}
        (BUILD / 'cases.txt').write_text(''.join(f'{n} {r}\n' for n, r in lengths.items()))
    if args.generate_only:
        return 0

    simulator = args.sim
    iv = shutil.which(os.environ.get('IVERILOG', 'iverilog'))
    vl = shutil.which(os.environ.get('VERILATOR', 'verilator'))
    if simulator == 'auto':
        simulator = 'iverilog' if iv else 'verilator'
    if args.netlist:
        simulator = 'iverilog'
    if (simulator == 'iverilog' and not iv) or (simulator == 'verilator' and not vl):
        raise SystemExit('No RTL simulator available. Install Icarus or Verilator; generation alone is not verification.')

    top = 'tb_cpu16'
    if args.netlist:
        files = [str(args.netlist), 'tb/tb_cpu16.sv']                   # black-box only: no WHITEBOX
        name = 'gate'
    else:
        files = [str(args.rtl / 'cpu16_core.v'), str(args.rtl / 'cpu16_alu.v'), 'tb/tb_cpu16.sv']
        name = 'rtl' if args.rtl == Path('rtl') else 'mut_' + args.rtl.name
    with (BUILD / f'{name}_compile.log').open('w') as log:
        if simulator == 'iverilog':
            defines = [] if args.netlist else ['-DWHITEBOX']
            rc = run([iv, '-g2012', '-Wall', *defines, '-s', top, '-o', BUILD / f'{name}_sim', *files],
                     stdout=log, stderr=subprocess.STDOUT).returncode
        else:
            rc = run([vl, '--binary', '--timing', '-Wno-fatal', '-Wno-lint', '-Wno-style', '-DWHITEBOX', '-j', '2',
                      '--top-module', top, '--Mdir', BUILD / f'obj_{name}', *files],
                     stdout=log, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        print((BUILD / f'{name}_compile.log').read_text())
        raise SystemExit('testbench compile failed')
    vvp = os.environ.get('VVP') or shutil.which('vvp') or 'vvp'
    exe = [vvp, BUILD / f'{name}_sim'] if simulator == 'iverilog' else [BUILD / f'obj_{name}' / f'V{top}']

    jobs = []
    names = sorted(lengths, key=lengths.get) if args.fail_fast else list(lengths)
    for n in names:
        modes = MODES if (not args.quick or n in ('directed', 'recursion', 'conditions')) else (1, 2)
        for m in modes:
            jobs.append((n, m, 0))
    reset_pool = [n for n in names if not n.startswith('fuzz') and lengths[n] < 3000]
    for n in reset_pool[: 6 if args.quick else 14]:
        jobs.append((n, 1 + (len(jobs) % 3), 3))
    jobs.append(('directed', 0, 5))

    def one(job):
        n, m, resets = job
        cmd = exe + [f'+IMAGE=build/{n}.hex', f'+TRACE=build/{n}.trace', f'+MODE={m}', f'+RESETS={resets}',
                     f'+SEED={len(n) * 31 + m}']
        proc = run(cmd, capture_output=True, text=True)
        out = proc.stdout + proc.stderr
        ok = proc.returncode == 0 and 'PASS:' in out and 'FATAL' not in out and 'Error' not in out
        return job, ok, out

    failures = 0
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(one, j) for j in jobs]
        for fut in cf.as_completed(futures) if args.fail_fast else futures:
            job, ok, out = fut.result()
            if not ok:
                failures += 1
                lines = [l for l in out.splitlines() if 'FATAL' in l or 'rror' in l or 'PASS' in l]
                print(f'FAIL {job}: ' + (lines[0] if lines else out[-200:]))
                if args.fail_fast:
                    for f in futures: f.cancel()
                    break
    if failures:
        print(f'{failures} of {len(jobs)} simulation runs FAILED')
        return 1
    print(f'PASS: {len(jobs)} {"netlist" if args.netlist else "RTL"} simulation runs under {simulator} '
          f'({total} reference instructions x memory modes; every instruction checked).')
    return 0

if __name__ == '__main__':
    sys.exit(main())
