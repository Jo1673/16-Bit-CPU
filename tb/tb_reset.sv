`timescale 1ns/1ps
// Directed reset checks (white-box; compile with the RTL, not a netlist).
// Reset must cancel a stalled store, a stalled fetch and a stalled extension fetch, clear all
// architectural state, restart at address 0, and release HALT. The randomized mid-run reset
// tests in tb_cpu16 (+RESETS=n) complement this.
module tb_reset;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;
    wire [15:0] ia, da, wd;
    wire iv, dv, we, halted;
    reg ir = 1, dr = 0;
    reg [15:0] imem [0:15];
    integer i, writes = 0;
    cpu16_core dut(.clk(clk), .rst_n(rst_n), .imem_addr(ia), .imem_valid(iv),
        .imem_rdata(imem[ia[3:0]]), .imem_ready(ir), .dmem_addr(da), .dmem_wdata(wd),
        .dmem_valid(dv), .dmem_we(we), .dmem_rdata(16'h0000), .dmem_ready(dr), .halted(halted));
    always @(posedge clk) if (dv && dr && we && rst_n) writes = writes + 1;
    task reset_check;
        begin
            @(negedge clk); rst_n = 0;
            #1; if (iv || dv || we) $fatal(1, "request issued during reset");
            @(posedge clk); #1;
            if (dut.pc !== 0 || halted || dut.flag_z || dut.flag_c || dut.flag_n || dut.flag_v || dut.state !== 2'd0)
                $fatal(1, "reset did not clear control state");
            for (i = 1; i < 8; i = i + 1) if (dut.regs[i] !== 0) $fatal(1, "reset did not clear R%0d", i);
            @(negedge clk); rst_n = 1;
        end
    endtask
    initial begin
        for (i = 0; i < 16; i = i + 1) imem[i] = 0;
        imem[0] = 16'h1207;   // LDI R1,7
        imem[1] = 16'h9300;   // ST R1,[ext]
        imem[2] = 16'h8000;
        imem[3] = 16'hf000;   // HALT
        repeat (2) @(negedge clk);
        rst_n = 1;
        wait (dv && we);                       // stalled store request is up (dr = 0)
        repeat (4) @(negedge clk);
        reset_check();
        if (writes != 0) $fatal(1, "a stalled store was committed by reset");
        ir = 0;                                // reset while the first fetch is stalled
        repeat (4) @(negedge clk);
        reset_check();
        ir = 1;
        wait (dut.state == 2'd1);              // reset while the extension fetch is stalled
        @(negedge clk); ir = 0;
        reset_check();
        ir = 1; dr = 1;
        wait (halted);
        #1;
        if (writes != 1) $fatal(1, "expected exactly one completed store, got %0d", writes);
        reset_check();                         // reset leaves HALT
        if (halted) $fatal(1, "reset did not leave HALT");
        wait (halted);                         // and the program runs again from address 0
        #1;
        if (writes != 2) $fatal(1, "restart after reset did not store once more (%0d)", writes);
        $display("PASS: reset cancels pending requests, clears state, restarts and leaves HALT");
        $finish;
    end
    initial begin #20000; $fatal(1, "reset test timeout"); end
endmodule
