#!/usr/bin/env python3
"""Mutation test: inject one RTL fault at a time and require the regression to catch it.

A passing regression only means something if it can fail. Each mutant below is a plausible design
mistake (wrong flag, wrong condition, ignored ready, missing reset, ...). A mutant is KILLED when
tools/verify.py (quick matrix) or tb/tb_reset.sv fails on it. Survivors are listed and make the
script exit non-zero, unless they are documented in EQUIVALENT.
"""
import concurrent.futures as cf
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MUT = ROOT / 'build' / 'mut'

CORE, ALU = 'cpu16_core.v', 'cpu16_alu.v'
M = [  # (name, file, old text (must occur exactly once), new text)
 ('alu: overflow sign test inverted', ALU, 'overflow = (a[15] == b_eff[15])', 'overflow = (a[15] != b_eff[15])'),
 ('alu: carry out inverted', ALU, 'carry    = sum[16];', 'carry    = ~sum[16];'),
 ('alu: SUB carry-in forced 0', ALU, "(op == ALU_SUB) ? 1'b1 :", "(op == ALU_SUB) ? 1'b0 :"),
 ('alu: SBC ignores carry', ALU, '((op == ALU_ADC) || (op == ALU_SBC)) ? carry_in', '(op == ALU_ADC) ? carry_in'),
 ('alu: SBC does not invert b', ALU, 'wire        invert_b = (op == ALU_SUB) || (op == ALU_SBC);', 'wire        invert_b = (op == ALU_SUB);'),
 ('alu: SAR is logical', ALU, 'y = {a[15], a[15:1]};', "y = {1'b0, a[15:1]};"),
 ('alu: RCR ignores carry', ALU, 'y = {carry_in, a[15:1]};', "y = {1'b0, a[15:1]};"),
 ('alu: SHL carry from wrong bit', ALU, 'carry = a[15]; end', 'carry = a[14]; end'),
 ('alu: SHR carry from wrong bit', ALU, 'carry = a[0];  end\n            ALU_SAR', 'carry = a[15]; end\n            ALU_SAR'),
 ('alu: NOT inverts a', ALU, 'ALU_NOT: y = ~b;', 'ALU_NOT: y = ~a;'),
 ('alu: XOR becomes OR', ALU, 'ALU_XOR: y = a ^ b;', 'ALU_XOR: y = a | b;'),
 ('alu: MOV passes a', ALU, 'ALU_MOV: y = b;', 'ALU_MOV: y = a;'),
 ('cond: HS inverted', CORE, 'cond_met = flag_c;                          // HS', 'cond_met = !flag_c;                         // HS'),
 ('cond: HI ignores Z', CORE, 'cond_met = flag_c && !flag_z;', 'cond_met = flag_c;'),
 ('cond: LS ignores Z', CORE, 'cond_met = !flag_c || flag_z;', 'cond_met = !flag_c;'),
 ('cond: GE uses N only', CORE, 'cond_met = (flag_n == flag_v);              // GE', 'cond_met = !flag_n;              // GE'),
 ('cond: GT ignores Z', CORE, 'cond_met = !flag_z && (flag_n == flag_v);', 'cond_met = (flag_n == flag_v);'),
 ('cond: LE ignores Z', CORE, 'cond_met = flag_z || (flag_n != flag_v);', 'cond_met = (flag_n != flag_v);'),
 ('cond: MI tests V', CORE, 'cond_met = flag_n;                          // MI', 'cond_met = flag_v;                          // MI'),
 ('cond: VS tests C', CORE, 'cond_met = flag_v;                          // VS', 'cond_met = flag_c;                          // VS'),
 ('cond: reserved cc 15 always taken', CORE, "default: cond_met = 1'b0;", "default: cond_met = 1'b1;"),
 ('decode: BCC has no extension word', CORE, '(f_wide_kind && imem_rdata[8]) || f_bcc;', '(f_wide_kind && imem_rdata[8]);'),
 ('decode: ADDI cannot be wide', CORE, '(f_op == OP_JNZ) ||\n                        (f_op == OP_ADDI);', '(f_op == OP_JNZ);'),
 ('decode: function 0x30..0x3f act as BCC', CORE, "wire f_bcc        = (f_op == OP_GRP0) && (imem_rdata[5:4] == 2'b01);", "wire f_bcc        = (f_op == OP_GRP0) && (imem_rdata[4] == 1'b1);"),
 ('decode: is_bcc too wide', CORE, "wire        is_bcc = grp0 && (func[5:4] == 2'b01);", "wire        is_bcc = grp0 && (func[4] == 1'b1);"),
 ('pc: HALT advances PC', CORE, "if (!f_halt) pc <= pc + 16'd1;", "pc <= pc + 16'd1;"),
 ('pc: JZ inverted', CORE, 'OP_JZ:  if (flag_z)  pc <= operand;', 'OP_JZ:  if (!flag_z) pc <= operand;'),
 ('pc: JNZ inverted', CORE, 'OP_JNZ: if (!flag_z) pc <= operand;', 'OP_JNZ: if (flag_z)  pc <= operand;'),
 ('pc: JR uses rd', CORE, 'F_JR, F_JALR:        pc <= rs_value;', 'F_JR, F_JALR:        pc <= rd_value;'),
 ('link: JALR link off by one', CORE, 'F_JALR:       begin wr_en = 1\'b1; wr_data = pc; end', 'F_JALR:       begin wr_en = 1\'b1; wr_data = pc - 16\'d1; end'),
 ('link: BAL link is the target', CORE, 'if (is_bcc && cond_met) begin wr_en = 1\'b1; wr_data = pc; end', 'if (is_bcc && cond_met) begin wr_en = 1\'b1; wr_data = operand; end'),
 ('link: untaken branch writes link', CORE, 'if (is_bcc && cond_met) begin wr_en', 'if (is_bcc) begin wr_en'),
 ('stack: PUSH increments', CORE, "((func == F_PUSH) ? 16'hFFFF : 16'h0001)", "((func == F_PUSH) ? 16'h0001 : 16'hFFFF)"),
 ('stack: PUSH stores at old pointer', CORE, 'F_PUSH:              begin operand <= rs_step; ', 'F_PUSH:              begin operand <= rs_value;'),
 ('stack: POP does not go to MEMORY', CORE, 'F_LDX, F_STX, F_POP: begin', 'F_LDX, F_STX:        begin'),
 ('stack: pointer update writes rd', CORE, "F_PUSH, F_POP: begin wr_en = 1'b1; wr_idx = rs;", "F_PUSH, F_POP: begin wr_en = 1'b1; wr_idx = rd;"),
 ('mem: store data from rs', CORE, 'assign dmem_wdata = rd_value;', 'assign dmem_wdata = rs_value;'),
 ('mem: indirect store does not drive we', CORE, 'assign dmem_we    = dmem_valid && is_store;', 'assign dmem_we    = dmem_valid && (opcode == OP_ST);'),
 ('mem: dmem_valid ignores reset', CORE, 'assign dmem_valid = rst_n && !halted &&', 'assign dmem_valid = !halted &&'),
 ('mem: imem_valid ignores reset', CORE, 'assign imem_valid = rst_n && !halted &&', 'assign imem_valid = !halted &&'),
 ('mem: load ignores ready', CORE, 'state == MEMORY && dmem_ready && is_load', 'state == MEMORY && is_load'),
 ('mem: MEMORY ignores ready', CORE, 'MEMORY: if (dmem_ready) state <= FETCH;', 'MEMORY: state <= FETCH;'),
 ('mem: FETCH ignores ready', CORE, 'FETCH: if (imem_ready) begin', 'FETCH: begin'),
 ('mem: EXTENSION ignores ready', CORE, 'EXTENSION: if (imem_ready) begin', 'EXTENSION: begin'),
 ('mem: ST skips MEMORY', CORE, 'OP_LD, OP_ST: state <= MEMORY;', 'OP_LD: state <= MEMORY;'),
 ('mem: short immediate sign-extended', CORE, "operand     <= {8'b0, imem_rdata[7:0]};", "operand     <= {{8{imem_rdata[7]}}, imem_rdata[7:0]};"),
 ('flags: ADD does not set V', CORE, "OP_ADD, OP_SUB, OP_ADDI: begin\n                    wr_en = 1'b1; upd_zn = 1'b1; upd_c = 1'b1; upd_v = 1'b1;", "OP_ADD, OP_SUB, OP_ADDI: begin\n                    wr_en = 1'b1; upd_zn = 1'b1; upd_c = 1'b1;"),
 ('flags: CMP does not set C', CORE, "OP_CMP: begin upd_zn = 1'b1; upd_c = 1'b1; upd_v = 1'b1; end", "OP_CMP: begin upd_zn = 1'b1; upd_v = 1'b1; end"),
 ('flags: logic ops clobber C', CORE, "OP_AND, OP_OR, OP_XOR, OP_MOV: begin wr_en = 1'b1; upd_zn = 1'b1; end", "OP_AND, OP_OR, OP_XOR, OP_MOV: begin wr_en = 1'b1; upd_zn = 1'b1; upd_c = 1'b1; end"),
 ('flags: NOT clobbers C', CORE, "F_NOT:        begin wr_en = 1'b1; upd_zn = 1'b1; end", "F_NOT:        begin wr_en = 1'b1; upd_zn = 1'b1; upd_c = 1'b1; end"),
 ('flags: N from wrong bit', CORE, 'flag_n <= zn_val[15];', 'flag_n <= zn_val[14];'),
 ('flags: LDI does not set Z/N', CORE, "upd_zn = 1'b1; zn_val = operand;", "upd_zn = 1'b0; zn_val = operand;"),
 ('flags: load does not set Z/N', CORE, "upd_zn = 1'b1; zn_val = dmem_rdata;", "zn_val = dmem_rdata;"),
 ('alu: ADDI uses register', CORE, 'wire [15:0] alu_b = (opcode == OP_ADDI) ? operand : rs_value;', 'wire [15:0] alu_b = rs_value;'),
 ('alu: CMP adds', CORE, 'OP_SUB, OP_CMP: alu_op = ALU_SUB;', 'OP_SUB: alu_op = ALU_SUB;'),
 ('alu: SBC maps to SUB', CORE, 'F_SBC:   alu_op = ALU_SBC;', 'F_SBC:   alu_op = ALU_SUB;'),
 ('exec: HALT does not halt', CORE, "OP_HALT: halted <= 1'b1;", "OP_HALT: halted <= 1'b0;"),
 ('reset: R1 not cleared', CORE, 'for (i = 1; i < 8; i = i + 1) regs[i] <= 16\'b0;', 'for (i = 2; i < 8; i = i + 1) regs[i] <= 16\'b0;'),
 ('reset: PC restarts at 1', CORE, "pc          <= 16'b0;", "pc          <= 16'd1;"),
 ('reset: C flag not cleared', CORE, "flag_z <= 1'b0; flag_c <= 1'b0;", "flag_z <= 1'b0;"),
 ('reset: state not cleared', CORE, "state       <= FETCH;\n            pc ", "pc "),
]
# Mutants that cannot change observable behaviour would be listed here with a reason.
EQUIVALENT = {}

def run_mutant(index):
    name, fname, old, new = M[index]
    work = MUT / f'm{index}'
    if work.exists(): shutil.rmtree(work)
    shutil.copytree(ROOT / 'rtl', work)
    text = (work / fname).read_text()
    if text.count(old) != 1:
        return index, 'BAD', f'pattern occurs {text.count(old)} times'
    (work / fname).write_text(text.replace(old, new))
    env = dict(os.environ)
    cmd = [sys.executable, 'tools/verify.py', '--quick', '--reuse', '--fail-fast', '--jobs', '1', '--rtl', str(work.relative_to(ROOT))]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    out = proc.stdout + proc.stderr
    if 'testbench compile failed' in out or 'syntax error' in out:
        return index, 'BAD', 'mutant does not compile'
    if proc.returncode != 0:
        line = next((l for l in out.splitlines() if l.startswith('FAIL')), 'failed')
        return index, 'KILLED', line[:150]
    # the directed reset test has its own chance to catch reset mutants
    sim = work / 'tb_reset_sim'
    rc = subprocess.run(['iverilog', '-g2012', '-s', 'tb_reset', '-o', str(sim), str(work / CORE), str(work / ALU), 'tb/tb_reset.sv'],
                        cwd=ROOT, capture_output=True, text=True)
    if rc.returncode == 0:
        r = subprocess.run(['vvp', str(sim)], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0 or 'FATAL' in r.stdout + r.stderr or 'PASS' not in r.stdout:
            return index, 'KILLED', 'tb_reset'
    return index, 'SURVIVED', ''

def main():
    MUT.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, 'tools/verify.py', '--quick', '--generate-only'], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    results = []
    with cf.ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        for index, status, info in pool.map(run_mutant, range(len(M))):
            print(f'{status:8s} {M[index][0]:44s} {info}', flush=True)
            results.append((index, status))
    killed = sum(1 for _, s in results if s == 'KILLED')
    bad = [M[i][0] for i, s in results if s == 'BAD']
    survivors = [M[i][0] for i, s in results if s == 'SURVIVED' and M[i][0] not in EQUIVALENT]
    print(f'\n{killed} of {len(M)} mutants killed; {len(bad)} invalid; {len(survivors)} survivors')
    for s in survivors: print('  SURVIVED:', s)
    for s in bad: print('  INVALID :', s)
    shutil.rmtree(MUT, ignore_errors=True)
    return 1 if survivors or bad else 0

if __name__ == '__main__':
    sys.exit(main())
