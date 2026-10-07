`timescale 1ns/1ps
`default_nettype none

module tb_cpu8_core;
    reg         clk;
    reg         rst_n;
    wire [7:0]  imem_addr;
    wire [15:0] imem_rdata;
    wire [7:0]  dmem_addr;
    wire [7:0]  dmem_wdata;
    wire [7:0]  dmem_rdata;
    wire        dmem_we;
    wire        halted;

    reg [15:0] imem [0:255];
    reg [7:0]  dmem [0:255];

    integer i;
    integer cycles;

    assign imem_rdata = imem[imem_addr];
    assign dmem_rdata = dmem[dmem_addr];

    cpu8_core dut (
        .clk        (clk),
        .rst_n      (rst_n),
        .imem_addr  (imem_addr),
        .imem_rdata (imem_rdata),
        .dmem_addr  (dmem_addr),
        .dmem_wdata (dmem_wdata),
        .dmem_rdata (dmem_rdata),
        .dmem_we    (dmem_we),
        .halted     (halted)
    );

    always #5 clk = ~clk;

    always @(posedge clk) begin
        if (dmem_we)
            dmem[dmem_addr] <= dmem_wdata;
    end

    initial begin
        $dumpfile("cpu8.vcd");
        $dumpvars(0, tb_cpu8_core);

        clk = 1'b0;
        rst_n = 1'b0;
        cycles = 0;

        for (i = 0; i < 256; i = i + 1) begin
            imem[i] = 16'h0000; // NOP
            dmem[i] = 8'h00;
        end

        // Test program:
        // R1 = 5
        // R2 = 7
        // R1 = R1 + R2 = 12
        // MEM[0x20] = R1
        // R3 = 12
        // CMP R1,R3  -> Z=1
        // JZ 0x08    -> skip bad R4 write
        // R5 = MEM[0x20]
        // R5 = R5 + 1 = 13
        // MEM[0x21] = R5
        // HALT
        imem[8'h00] = 16'h1205; // LDI  R1, 0x05
        imem[8'h01] = 16'h1407; // LDI  R2, 0x07
        imem[8'h02] = 16'h2280; // ADD  R1, R2
        imem[8'h03] = 16'h9220; // ST   R1, [0x20]
        imem[8'h04] = 16'h160C; // LDI  R3, 0x0C
        imem[8'h05] = 16'hE2C0; // CMP  R1, R3
        imem[8'h06] = 16'hB008; // JZ   0x08
        imem[8'h07] = 16'h18EE; // LDI  R4, 0xEE (must be skipped)
        imem[8'h08] = 16'h8A20; // LD   R5, [0x20]
        imem[8'h09] = 16'hDA01; // ADDI R5, 0x01
        imem[8'h0A] = 16'h9A21; // ST   R5, [0x21]
        imem[8'h0B] = 16'hF000; // HALT

        repeat (3) @(posedge clk);
        @(negedge clk);
        rst_n = 1'b1;

        while (!halted && cycles < 100) begin
            @(posedge clk);
            cycles = cycles + 1;
        end

        // Wait one delta/half-cycle so the final nonblocking updates settle.
        #1;

        if (!halted) begin
            $display("FAIL: CPU did not halt");
            $finish;
        end
        if (dut.regs[1] !== 8'd12) begin
            $display("FAIL: R1 expected 12, got %0d", dut.regs[1]);
            $finish;
        end
        if (dut.regs[4] !== 8'h00) begin
            $display("FAIL: branch failed; R4=%02h", dut.regs[4]);
            $finish;
        end
        if (dut.regs[5] !== 8'd13) begin
            $display("FAIL: R5 expected 13, got %0d", dut.regs[5]);
            $finish;
        end
        if (dmem[8'h20] !== 8'd12) begin
            $display("FAIL: MEM[20] expected 12, got %0d", dmem[8'h20]);
            $finish;
        end
        if (dmem[8'h21] !== 8'd13) begin
            $display("FAIL: MEM[21] expected 13, got %0d", dmem[8'h21]);
            $finish;
        end

        $display("PASS: cpu8_core completed test program in %0d cycles", cycles);
        $display("R1=%0d R2=%0d R3=%0d R4=%0d R5=%0d", dut.regs[1], dut.regs[2], dut.regs[3], dut.regs[4], dut.regs[5]);
        $display("MEM[20]=%0d MEM[21]=%0d", dmem[8'h20], dmem[8'h21]);
        $finish;
    end
endmodule

`default_nettype wire
