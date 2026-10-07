`timescale 1ns/1ps
`default_nettype none
// CPU16 ALU. Operations 0..5 keep the CPU8 numbering (ADD SUB AND OR XOR MOV).
// Carry follows the ARM convention: for SUB/SBC, carry = 1 means "no borrow".
//   ADD/ADC : y = a + b (+ carry_in)         carry = unsigned carry out
//   SUB/SBC : y = a - b (- !carry_in)        carry = NOT borrow (a >= b for SUB)
//   overflow = signed overflow of the arithmetic operation
//   shifts  : operate on a; carry = the bit shifted out
module cpu16_alu (
    input  wire [3:0]  op,
    input  wire [15:0] a, b,
    input  wire        carry_in,
    output reg  [15:0] y,
    output reg         carry,
    output reg         overflow
);
    localparam [3:0] ALU_ADD = 4'd0,  ALU_SUB = 4'd1,  ALU_AND = 4'd2,
                     ALU_OR  = 4'd3,  ALU_XOR = 4'd4,  ALU_MOV = 4'd5,
                     ALU_ADC = 4'd6,  ALU_SBC = 4'd7,  ALU_NOT = 4'd8,
                     ALU_SHL = 4'd9,  ALU_SHR = 4'd10, ALU_SAR = 4'd11,
                     ALU_RCR = 4'd12;

    wire        invert_b = (op == ALU_SUB) || (op == ALU_SBC);
    wire [15:0] b_eff    = invert_b ? ~b : b;
    wire        cin      = (op == ALU_SUB) ? 1'b1 :
                           ((op == ALU_ADC) || (op == ALU_SBC)) ? carry_in : 1'b0;
    wire [16:0] sum      = {1'b0, a} + {1'b0, b_eff} + {16'b0, cin};

    always @* begin
        y        = 16'h0000;
        carry    = 1'b0;
        overflow = 1'b0;
        case (op)
            ALU_ADD, ALU_SUB, ALU_ADC, ALU_SBC: begin
                y        = sum[15:0];
                carry    = sum[16];
                overflow = (a[15] == b_eff[15]) && (sum[15] != a[15]);
            end
            ALU_AND: y = a & b;
            ALU_OR:  y = a | b;
            ALU_XOR: y = a ^ b;
            ALU_MOV: y = b;
            ALU_NOT: y = ~b;
            ALU_SHL: begin y = {a[14:0], 1'b0};     carry = a[15]; end
            ALU_SHR: begin y = {1'b0, a[15:1]};     carry = a[0];  end
            ALU_SAR: begin y = {a[15], a[15:1]};    carry = a[0];  end
            ALU_RCR: begin y = {carry_in, a[15:1]}; carry = a[0];  end
            default: y = 16'h0000;
        endcase
    end
endmodule
`default_nettype wire
