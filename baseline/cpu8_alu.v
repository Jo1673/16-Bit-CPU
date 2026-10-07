`timescale 1ns/1ps
`default_nettype none

module cpu8_alu (
    input  wire [2:0] op,
    input  wire [7:0] a,
    input  wire [7:0] b,
    output reg  [7:0] y,
    output wire       zero
);
    localparam ALU_ADD = 3'd0;
    localparam ALU_SUB = 3'd1;
    localparam ALU_AND = 3'd2;
    localparam ALU_OR  = 3'd3;
    localparam ALU_XOR = 3'd4;
    localparam ALU_MOV = 3'd5;

    always @* begin
        case (op)
            ALU_ADD: y = a + b;
            ALU_SUB: y = a - b;
            ALU_AND: y = a & b;
            ALU_OR : y = a | b;
            ALU_XOR: y = a ^ b;
            ALU_MOV: y = b;
            default: y = 8'h00;
        endcase
    end

    assign zero = (y == 8'h00);
endmodule

`default_nettype wire
