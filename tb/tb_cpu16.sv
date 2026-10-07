`timescale 1ns/1ps
// Differential testbench: the RTL (or a synthesized netlist) against tools/model16.py traces.
//
// Black-box checks (always on; they use ONLY the ports, so they also run on a gate netlist):
//   * every accepted instruction fetch and data transfer matches the model, in order
//     (addresses, store data, load/store direction, extension-word fetches)
//   * with MODE=0 the cycle count of every instruction equals the documented timing
//   * requests stay stable while a response is pending; no outputs are X; nothing happens after HALT
//   * no request is issued while rst_n is low
// White-box checks (only with +define+WHITEBOX): PC, flags and R1..R7 after every instruction.
//
// +MODE=0 ready always high, combinational data
//      1 random ready, garbage data whenever ready is low
//      2 registered SRAM: ready one cycle after the request, stale data otherwise
//      3 bursty: ready only after 0..15 idle cycles, garbage data otherwise
// +RESETS=n  asserts reset at n random points; the data memory is restored and the program must
//            restart from address 0 and still match from instruction zero.
module tb_cpu16;
    localparam MAXROWS = 16384;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    wire [15:0] ia, da, wd;
    wire iv, dv, we, halted;
    reg  [15:0] imem [0:65535];
    reg  [15:0] dmem [0:65535];
    reg  [15:0] tr   [0:MAXROWS*20-1];

    integer mode = 1, resets_left = 0, resets_total = 0, nrows = 0, est = 0;
    reg  [31:0] rs = 32'h2545F491;

    reg  ir = 0, dr = 0, s_ir = 0, s_dr = 0, i_pend = 0, d_pend = 0;
    reg  [15:0] s_id = 16'hDEAD, s_dd = 16'hBEEF, gi = 16'h1111, gd = 16'h2222;
    integer icnt = 0, dcnt = 0;
    wire        i_ready = (mode == 2) ? s_ir : ir;
    wire        d_ready = (mode == 2) ? s_dr : dr;
    wire [15:0] i_data  = (mode == 2) ? s_id : (ir ? imem[ia] : gi);
    wire [15:0] d_data  = (mode == 2) ? s_dd : (dr ? dmem[da] : gd);

    cpu16_core dut(.clk(clk), .rst_n(rst_n), .imem_addr(ia), .imem_valid(iv),
        .imem_rdata(i_data), .imem_ready(i_ready), .dmem_addr(da), .dmem_wdata(wd),
        .dmem_valid(dv), .dmem_we(we), .dmem_rdata(d_data), .dmem_ready(d_ready), .halted(halted));

    function [31:0] xs(input [31:0] x);
        reg [31:0] y;
        begin y = x ^ (x << 13); y = y ^ (y >> 17); y = y ^ (y << 5); xs = y; end
    endfunction
    function integer fld(input integer r, input integer k);
        fld = tr[r*20 + k];
    endfunction

    // ---------------- memory responder: modes 0, 1, 3 (ready/garbage change on falling edges)
    always @(negedge clk) begin
        rs = xs(rs);
        gi = rs[15:0] ^ 16'hA5C3;
        gd = rs[31:16] ^ 16'h3C5A;
        case (mode)
            0: begin ir = 1; dr = 1; end
            1: begin ir = rs[7]; dr = rs[19]; end
            3: begin
                if (ir) begin ir = 0; icnt = rs[11:8]; end
                else if (icnt == 0) ir = 1; else icnt = icnt - 1;
                if (dr) begin dr = 0; dcnt = rs[27:24]; end
                else if (dcnt == 0) dr = 1; else dcnt = dcnt - 1;
            end
            default: ;
        endcase
    end

    // ---------------- memory responder: mode 2 (registered, one-cycle-latency SRAM bridge)
    always @(posedge clk) if (mode == 2) begin
        if (!rst_n) begin s_ir <= 0; i_pend <= 0; s_dr <= 0; d_pend <= 0; end
        else begin
            if (iv && s_ir) begin s_ir <= 0; i_pend <= 0; s_id <= gi; end
            else if (iv && !i_pend) begin i_pend <= 1; s_ir <= 1; s_id <= imem[ia]; end
            if (dv && s_dr) begin s_dr <= 0; d_pend <= 0; s_dd <= gd; end
            else if (dv && !d_pend) begin d_pend <= 1; s_dr <= 1; s_dd <= dmem[da]; end
        end
    end

    // ---------------- scheduled mid-run resets
    integer cyc = 0, total = 0, reset_at = 0, hold = 0, started = 0;
    always @(negedge clk) begin
        if (started) begin
            if (hold > 0) begin hold = hold - 1; if (hold == 0) rst_n = 1; end
            else if (resets_left > 0 && cyc >= reset_at) begin
                rst_n = 0; hold = 1 + rs[9:8]; resets_left = resets_left - 1;
                reset_at = 1 + (rs[30:12] % (est > 2 ? est - 1 : 1));
            end
        end
    end

    // ---------------- monitor
    string image_path, trace_path;
    integer fd, rc, k, v, ri, nf, nd, i_seen, first_cyc, halt_cyc, halt_seen, tail, retired, post_reset;
    integer nfetch, ndata, expect_addr, prev_cycles;
    reg  wait_i, wait_d, old_we, i_acc, d_acc;
    reg  [15:0] old_ia, old_da, old_wd;
`ifdef WHITEBOX
    reg  [15:0] snap [1:7];
    reg  [3:0]  snapf;
    reg         snap_ok = 0;
`endif

    initial begin
        if (!$value$plusargs("IMAGE=%s", image_path)) $fatal(1, "missing +IMAGE");
        if (!$value$plusargs("TRACE=%s", trace_path)) $fatal(1, "missing +TRACE");
        if (!$value$plusargs("MODE=%d", mode)) mode = 1;
        if (!$value$plusargs("RESETS=%d", resets_left)) resets_left = 0;
        resets_total = resets_left;
        if ($value$plusargs("SEED=%d", v)) rs = xs(32'h2545F491 ^ v);
        if ($test$plusargs("VCD")) begin $dumpfile("build/cpu16.vcd"); $dumpvars(0, tb_cpu16); end
        for (k = 0; k < 65536; k = k + 1) begin imem[k] = 0; dmem[k] = (k * 32'h9E37 + 32'h3039) & 32'hFFFF; end
        $readmemh(image_path, imem);
        fd = $fopen(trace_path, "r");
        if (fd == 0) $fatal(1, "cannot open trace");
        k = 0;
        while ($fscanf(fd, "%h", v) == 1) begin
            if (k >= MAXROWS*20) $fatal(1, "trace too long");
            tr[k] = v; k = k + 1;
        end
        $fclose(fd);
        if (k % 20 != 0 || k == 0) $fatal(1, "malformed trace");
        nrows = k / 20;
        for (k = 0; k < nrows; k = k + 1) est = est + fld(k, 19);
        reset_at = 1 + (rs[30:12] % (est > 2 ? est - 1 : 1));
        ri = 0; nf = 0; nd = 0; i_seen = 0; halt_seen = 0; tail = 0; retired = 0; post_reset = 1;
        wait_i = 0; wait_d = 0; first_cyc = 0;
        repeat (3) @(negedge clk);
        started = 1; rst_n = 1;
    end

    always @(posedge clk) if (nrows != 0) begin
        total = total + 1;
        if (total > est * 40 + 5000) $fatal(1, "timeout: cycle %0d (expected about %0d)", total, est);
        if (!rst_n) begin
            if (iv !== 1'b0 || dv !== 1'b0 || we !== 1'b0) $fatal(1, "request issued while rst_n is low");
            ri = 0; nf = 0; nd = 0; i_seen = 0; cyc = 0; wait_i = 0; wait_d = 0; halt_seen = 0;
            tail = 0; retired = 0; post_reset = 1;
`ifdef WHITEBOX
            snap_ok = 0;
`endif
            for (k = 0; k < 65536; k = k + 1) dmem[k] = (k * 32'h9E37 + 32'h3039) & 32'hFFFF;
        end else begin
            cyc = cyc + 1;
`ifdef WHITEBOX
            // Architectural state may change only when an instruction executes or a data transfer
            // completes: never while fetching or while a load/store is still waiting for ready.
            if (snap_ok) begin
                for (k = 1; k < 8; k = k + 1)
                    if (dut.regs[k] !== snap[k]) $fatal(1, "R%0d changed outside EXECUTE/MEMORY completion (cycle %0d)", k, cyc);
                if ({dut.flag_z, dut.flag_c, dut.flag_n, dut.flag_v} !== snapf)
                    $fatal(1, "flags changed outside EXECUTE/MEMORY completion (cycle %0d)", cyc);
            end
            snap_ok = (dut.state == 2'd0) || (dut.state == 2'd1) || (dut.state == 2'd3 && !d_ready);
            for (k = 1; k < 8; k = k + 1) snap[k] = dut.regs[k];
            snapf = {dut.flag_z, dut.flag_c, dut.flag_n, dut.flag_v};
`endif
            if (post_reset) begin
                if (halted !== 1'b0) $fatal(1, "halted not cleared by reset");
`ifdef WHITEBOX
                if (dut.state !== 2'd0 || dut.pc !== 16'd0 || dut.flag_z !== 1'b0 || dut.flag_c !== 1'b0 ||
                    dut.flag_n !== 1'b0 || dut.flag_v !== 1'b0) $fatal(1, "control state not cleared by reset");
                for (k = 1; k < 8; k = k + 1) if (dut.regs[k] !== 16'd0) $fatal(1, "R%0d not cleared by reset", k);
`endif
                post_reset = 0;
            end
            if ((^{iv, dv, we, halted}) === 1'bx) $fatal(1, "X on a control output at cycle %0d", cyc);
            if (iv && ((^ia) === 1'bx)) $fatal(1, "X on imem_addr while valid");
            if (dv && ((^da) === 1'bx || (we && (^wd) === 1'bx))) $fatal(1, "X on dmem_addr/wdata while valid");
            if (wait_i && !(iv && ia === old_ia)) $fatal(1, "instruction request changed while waiting (cycle %0d)", cyc);
            if (wait_d && !(dv && da === old_da && we === old_we && (!we || wd === old_wd)))
                $fatal(1, "data request changed while waiting (cycle %0d)", cyc);
            wait_i = iv && !i_ready; old_ia = ia;
            wait_d = dv && !d_ready; old_da = da; old_we = we; old_wd = wd;
            i_acc = iv && i_ready;
            d_acc = dv && d_ready;
            if (halt_seen) begin
                if (iv || dv || we || !halted) $fatal(1, "bus not quiescent after HALT");
                tail = tail + 1;
                if (tail == 6) begin
                    if (resets_left != 0) $fatal(1, "program ended before %0d scheduled resets", resets_left);
                    $display("PASS: %0s mode=%0d resets=%0d retired=%0d cycles=%0d", image_path, mode, resets_total, nrows, cyc);
                    $finish;
                end
            end
            if (i_acc) begin
                if (i_seen) begin
                    nfetch = fld(ri, 19) - 1 - ((fld(ri, 14) | fld(ri, 17)) ? 1 : 0);
                    ndata  = (fld(ri, 14) | fld(ri, 17)) ? 1 : 0;
                    if (nf == nfetch && nd == ndata) begin
                        prev_cycles = fld(ri, 19);
                        if (mode == 0 && cyc - first_cyc != prev_cycles)
                            $fatal(1, "instruction %0d took %0d cycles, expected %0d", ri, cyc - first_cyc, prev_cycles);
                        ri = ri + 1; nf = 0; nd = 0;
                    end
                end else if (mode == 0 && cyc != 1) $fatal(1, "first fetch at cycle %0d, expected 1", cyc);
                if (ri >= nrows) $fatal(1, "instruction fetch after the traced program ended");
                nfetch = fld(ri, 19) - 1 - ((fld(ri, 14) | fld(ri, 17)) ? 1 : 0);
                if (nf >= nfetch || (nf != 0 && nd != 0)) $fatal(1, "unexpected extra fetch in instruction %0d", ri);
                expect_addr = (ri == 0) ? 0 : fld(ri - 1, 0);
                if (nf == 1) expect_addr = (expect_addr + 1) & 16'hFFFF;
                if (ia !== expect_addr[15:0])
                    $fatal(1, "instruction %0d fetch %0d from %h, expected %h", ri, nf, ia, expect_addr[15:0]);
                if (nf == 0) first_cyc = cyc;
                nf = nf + 1; i_seen = 1;
            end
            if (d_acc) begin
                nfetch = fld(ri, 19) - 1 - ((fld(ri, 14) | fld(ri, 17)) ? 1 : 0);
                if (!i_seen || nf != nfetch || nd != 0 || !(fld(ri, 14) | fld(ri, 17)))
                    $fatal(1, "unexpected data transfer in instruction %0d", ri);
                if (fld(ri, 14)) begin
                    if (we !== 1'b1 || da !== fld(ri, 15) || wd !== fld(ri, 16))
                        $fatal(1, "instruction %0d store %h<=%h (we=%b), expected %h<=%h", ri, da, wd, we, fld(ri, 15), fld(ri, 16));
                    dmem[da] <= wd;
                end else if (we !== 1'b0 || da !== fld(ri, 18))
                    $fatal(1, "instruction %0d load %h (we=%b), expected %h", ri, da, we, fld(ri, 18));
                nd = nd + 1;
            end
            if (halted === 1'b1 && !halt_seen) begin
                if (ri != nrows - 1 || !i_seen) $fatal(1, "halted early at instruction %0d of %0d", ri, nrows);
                if (mode == 0 && cyc - first_cyc != fld(ri, 19)) $fatal(1, "HALT timing: %0d cycles", cyc - first_cyc);
                halt_seen = 1; tail = 0;
            end
`ifdef WHITEBOX
            if (dut.retire === 1'b1) begin
                if (!i_seen) $fatal(1, "retire before any fetch");
                #1;
                if (dut.pc !== fld(ri, 0) || dut.flag_z !== fld(ri, 1) || dut.flag_c !== fld(ri, 2) ||
                    dut.flag_n !== fld(ri, 3) || dut.flag_v !== fld(ri, 4) || halted !== fld(ri, 5))
                    $fatal(1, "instruction %0d: pc/Z/C/N/V/H got %h/%b/%b/%b/%b/%b expected %h/%0d/%0d/%0d/%0d/%0d", ri,
                           dut.pc, dut.flag_z, dut.flag_c, dut.flag_n, dut.flag_v, halted,
                           fld(ri, 0), fld(ri, 1), fld(ri, 2), fld(ri, 3), fld(ri, 4), fld(ri, 5));
                for (k = 1; k < 8; k = k + 1)
                    if (dut.regs[k] !== fld(ri, 6 + k)) $fatal(1, "instruction %0d: R%0d got %h expected %h", ri, k, dut.regs[k], fld(ri, 6 + k));
                retired = retired + 1;
            end
`endif
        end
    end
endmodule
