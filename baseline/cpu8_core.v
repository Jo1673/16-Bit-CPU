`timescale 1ns/1ps
`default_nettype none

module cpu8_core (
    input  wire        clk,
    input  wire        rst_n,

    // Instruction memory interface: 256 x 16-bit words.
    output wire [7:0]  imem_addr,
    input  wire [15:0] imem_rdata,

    // Data memory interface: 256 x 8-bit bytes.
    output reg  [7:0]  dmem_addr,
    output reg  [7:0]  dmem_wdata,
    input  wire [7:0]  dmem_rdata,
    output reg         dmem_we,

    output reg         halted
);
    // Fixed 16-bit instruction format.
    localparam OP_NOP  = 4'h0;
    localparam OP_LDI  = 4'h1;
    localparam OP_ADD  = 4'h2;
    localparam OP_SUB  = 4'h3;
    localparam OP_AND  = 4'h4;
    localparam OP_OR   = 4'h5;
    localparam OP_XOR  = 4'h6;
    localparam OP_MOV  = 4'h7;
    localparam OP_LD   = 4'h8;
    localparam OP_ST   = 4'h9;
    localparam OP_JMP  = 4'hA;
    localparam OP_JZ   = 4'hB;
    localparam OP_JNZ  = 4'hC;
    localparam OP_ADDI = 4'hD;
    localparam OP_CMP  = 4'hE;
    localparam OP_HALT = 4'hF;

    localparam ALU_ADD = 3'd0;
    localparam ALU_SUB = 3'd1;
    localparam ALU_AND = 3'd2;
    localparam ALU_OR  = 3'd3;
    localparam ALU_XOR = 3'd4;
    localparam ALU_MOV = 3'd5;

    reg [7:0] pc;
    reg [7:0] regs [0:7];
    reg       zero_flag;

    wire [3:0] opcode = imem_rdata[15:12];
    wire [2:0] rd     = imem_rdata[11:9];
    wire [2:0] rs     = imem_rdata[8:6];
    wire [7:0] imm8   = imem_rdata[7:0];

    wire [7:0] rd_value = (rd == 3'd0) ? 8'h00 : regs[rd];
    wire [7:0] rs_value = (rs == 3'd0) ? 8'h00 : regs[rs];

    reg  [2:0] alu_op;
    reg  [7:0] alu_a;
    reg  [7:0] alu_b;
    wire [7:0] alu_y;
    wire       alu_zero;

    integer i;

    cpu8_alu u_alu (
        .op   (alu_op),
        .a    (alu_a),
        .b    (alu_b),
        .y    (alu_y),
        .zero (alu_zero)
    );

    assign imem_addr = pc;

    always @* begin
        alu_op = ALU_ADD;
        alu_a  = rd_value;
        alu_b  = rs_value;

        case (opcode)
            OP_ADD : alu_op = ALU_ADD;
            OP_SUB : alu_op = ALU_SUB;
            OP_AND : alu_op = ALU_AND;
            OP_OR  : alu_op = ALU_OR;
            OP_XOR : alu_op = ALU_XOR;
            OP_MOV : begin
                alu_op = ALU_MOV;
                alu_b  = rs_value;
            end
            OP_ADDI: begin
                alu_op = ALU_ADD;
                alu_b  = imm8;
            end
            default: begin
                alu_op = ALU_ADD;
                alu_a  = rd_value;
                alu_b  = rs_value;
            end
        endcase
    end

    // Combinational data-memory interface. Stores are committed by the
    // external memory on the active clock edge when dmem_we is asserted.
    always @* begin
        dmem_addr  = imm8;
        dmem_wdata = rd_value;
        dmem_we    = 1'b0;

        if (!halted && opcode == OP_ST)
            dmem_we = 1'b1;
    end

    // Synchronous state updates. rst_n is an active-low synchronous reset.
    always @(posedge clk) begin
        if (!rst_n) begin
            pc        <= 8'h00;
            zero_flag <= 1'b0;
            halted    <= 1'b0;
            for (i = 0; i < 8; i = i + 1)
                regs[i] <= 8'h00;
        end else if (!halted) begin
            case (opcode)
                OP_NOP: begin
                    pc <= pc + 8'd1;
                end

                OP_LDI: begin
                    if (rd != 3'd0)
                        regs[rd] <= imm8;
                    zero_flag <= (imm8 == 8'h00);
                    pc <= pc + 8'd1;
                end

                OP_ADD, OP_SUB, OP_AND, OP_OR, OP_XOR, OP_MOV: begin
                    if (rd != 3'd0)
                        regs[rd] <= alu_y;
                    zero_flag <= alu_zero;
                    pc <= pc + 8'd1;
                end

                OP_LD: begin
                    if (rd != 3'd0)
                        regs[rd] <= dmem_rdata;
                    zero_flag <= (dmem_rdata == 8'h00);
                    pc <= pc + 8'd1;
                end

                OP_ST: begin
                    pc <= pc + 8'd1;
                end

                OP_JMP: begin
                    pc <= imm8;
                end

                OP_JZ: begin
                    if (zero_flag)
                        pc <= imm8;
                    else
                        pc <= pc + 8'd1;
                end

                OP_JNZ: begin
                    if (!zero_flag)
                        pc <= imm8;
                    else
                        pc <= pc + 8'd1;
                end

                OP_ADDI: begin
                    if (rd != 3'd0)
                        regs[rd] <= alu_y;
                    zero_flag <= alu_zero;
                    pc <= pc + 8'd1;
                end

                OP_CMP: begin
                    zero_flag <= (rd_value == rs_value);
                    pc <= pc + 8'd1;
                end

                OP_HALT: begin
                    halted <= 1'b1;
                    pc <= pc;
                end

                default: begin
                    pc <= pc + 8'd1;
                end
            endcase

            // R0 is permanently hard-wired to zero.
            regs[0] <= 8'h00;
        end
    end
endmodule

`default_nettype wire
