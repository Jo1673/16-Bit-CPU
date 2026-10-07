`timescale 1ns/1ps
`default_nettype none
// CPU16: multicycle 16-bit core derived from CPU8. See docs/ISA.md and docs/INTERFACE.md.
// All interfaces share clk. rst_n is active-low SYNCHRONOUS reset.
// A transfer occurs at a rising edge with valid && ready && rst_n.
module cpu16_core (
    input  wire        clk, rst_n,
    output wire [15:0] imem_addr,
    output wire        imem_valid,
    input  wire [15:0] imem_rdata,
    input  wire        imem_ready,
    output wire [15:0] dmem_addr,
    output wire [15:0] dmem_wdata,
    output wire        dmem_valid, dmem_we,
    input  wire [15:0] dmem_rdata,
    input  wire        dmem_ready,
    output reg         halted
);
    localparam [1:0] FETCH = 2'd0, EXTENSION = 2'd1, EXECUTE = 2'd2, MEMORY = 2'd3;

    // First-word opcodes. Opcode 0 is the NOP / extended group: bits [5:0] are a function code.
    localparam [3:0] OP_GRP0 = 4'h0, OP_LDI = 4'h1, OP_ADD = 4'h2, OP_SUB = 4'h3,
                     OP_AND  = 4'h4, OP_OR  = 4'h5, OP_XOR = 4'h6, OP_MOV = 4'h7,
                     OP_LD   = 4'h8, OP_ST  = 4'h9, OP_JMP = 4'ha, OP_JZ  = 4'hb,
                     OP_JNZ  = 4'hc, OP_ADDI = 4'hd, OP_CMP = 4'he, OP_HALT = 4'hf;
    // Opcode-0 function codes. Function 0 and every unlisted code behave as NOP;
    // codes 6'h10..6'h1f are conditional branches (is_bcc), condition in bits [3:0].
    localparam [5:0] F_ADC = 6'd1, F_SBC = 6'd2, F_NOT = 6'd3,
                     F_SHL = 6'd4, F_SHR = 6'd5, F_SAR = 6'd6, F_RCR = 6'd7,
                     F_LDX = 6'd8, F_STX = 6'd9, F_PUSH = 6'd10, F_POP = 6'd11,
                     F_JR  = 6'd12, F_JALR = 6'd13;
    localparam [3:0] ALU_ADD = 4'd0, ALU_SUB = 4'd1, ALU_AND = 4'd2, ALU_OR = 4'd3,
                     ALU_XOR = 4'd4, ALU_MOV = 4'd5, ALU_ADC = 4'd6, ALU_SBC = 4'd7,
                     ALU_NOT = 4'd8, ALU_SHL = 4'd9, ALU_SHR = 4'd10, ALU_SAR = 4'd11,
                     ALU_RCR = 4'd12;

    reg  [1:0]  state;
    reg  [15:0] pc, operand, instruction;
    reg  [15:0] regs [1:7];                // R0 has no storage: it reads as zero, writes vanish
    reg         flag_z, flag_c, flag_n, flag_v;

    wire [3:0]  opcode = instruction[15:12];
    wire [2:0]  rd     = instruction[11:9];
    wire [2:0]  rs     = instruction[8:6];
    wire [5:0]  func   = instruction[5:0];
    wire [3:0]  cc     = instruction[3:0];
    wire        grp0   = (opcode == OP_GRP0);
    wire        is_bcc = grp0 && (func[5:4] == 2'b01);

    // Register-file read ports. Written as always @* blocks (not a function call inside a
    // continuous assignment) so that every simulator re-evaluates them when a register changes.
    reg [15:0] rd_value, rs_value;
    always @* begin
        case (rd)
            3'd1: rd_value = regs[1];
            3'd2: rd_value = regs[2];
            3'd3: rd_value = regs[3];
            3'd4: rd_value = regs[4];
            3'd5: rd_value = regs[5];
            3'd6: rd_value = regs[6];
            3'd7: rd_value = regs[7];
            default: rd_value = 16'h0000;
        endcase
        case (rs)
            3'd1: rs_value = regs[1];
            3'd2: rs_value = regs[2];
            3'd3: rs_value = regs[3];
            3'd4: rs_value = regs[4];
            3'd5: rs_value = regs[5];
            3'd6: rs_value = regs[6];
            3'd7: rs_value = regs[7];
            default: rs_value = 16'h0000;
        endcase
    end
    // One shared +/-1 adder: PUSH pre-decrements the pointer, POP post-increments it.
    wire [15:0] rs_step  = rs_value + ((func == F_PUSH) ? 16'hFFFF : 16'h0001);

    // ---- decode of the word being fetched (used only when its fetch completes)
    wire [3:0] f_op   = imem_rdata[15:12];
    wire f_wide_kind  = (f_op == OP_LDI) || (f_op == OP_LD)  || (f_op == OP_ST)  ||
                        (f_op == OP_JMP) || (f_op == OP_JZ)  || (f_op == OP_JNZ) ||
                        (f_op == OP_ADDI);
    wire f_bcc        = (f_op == OP_GRP0) && (imem_rdata[5:4] == 2'b01);
    wire f_has_ext    = (f_wide_kind && imem_rdata[8]) || f_bcc;
    wire f_halt       = (f_op == OP_HALT);

    // ---- memory-operation classes
    wire is_load  = (opcode == OP_LD) ||
                    (grp0 && ((func == F_LDX) || (func == F_POP)));
    wire is_store = (opcode == OP_ST) ||
                    (grp0 && ((func == F_STX) || (func == F_PUSH)));

    // ---- ALU
    reg  [3:0]  alu_op;
    wire [15:0] alu_b = (opcode == OP_ADDI) ? operand : rs_value;
    wire [15:0] alu_y;
    wire        alu_carry, alu_overflow;
    integer i;

    cpu16_alu u_alu(.op(alu_op), .a(rd_value), .b(alu_b), .carry_in(flag_c),
                    .y(alu_y), .carry(alu_carry), .overflow(alu_overflow));

    always @* begin
        alu_op = ALU_ADD;
        case (opcode)
            OP_SUB, OP_CMP: alu_op = ALU_SUB;
            OP_AND:         alu_op = ALU_AND;
            OP_OR:          alu_op = ALU_OR;
            OP_XOR:         alu_op = ALU_XOR;
            OP_MOV:         alu_op = ALU_MOV;
            OP_GRP0: case (func)
                F_ADC:   alu_op = ALU_ADC;
                F_SBC:   alu_op = ALU_SBC;
                F_NOT:   alu_op = ALU_NOT;
                F_SHL:   alu_op = ALU_SHL;
                F_SHR:   alu_op = ALU_SHR;
                F_SAR:   alu_op = ALU_SAR;
                F_RCR:   alu_op = ALU_RCR;
                default: alu_op = ALU_ADD;
            endcase
            default:        alu_op = ALU_ADD;
        endcase
    end

    // ---- branch condition (cc = instruction[3:0]); carry is "no borrow" after a subtract
    reg cond_met;
    always @* begin
        case (cc)
            4'd0:    cond_met = flag_z;                          // EQ
            4'd1:    cond_met = !flag_z;                         // NE
            4'd2:    cond_met = flag_c;                          // HS  unsigned >=
            4'd3:    cond_met = !flag_c;                         // LO  unsigned <
            4'd4:    cond_met = flag_n;                          // MI
            4'd5:    cond_met = !flag_n;                         // PL
            4'd6:    cond_met = flag_v;                          // VS
            4'd7:    cond_met = !flag_v;                         // VC
            4'd8:    cond_met = flag_c && !flag_z;               // HI  unsigned >
            4'd9:    cond_met = !flag_c || flag_z;               // LS  unsigned <=
            4'd10:   cond_met = (flag_n == flag_v);              // GE  signed >=
            4'd11:   cond_met = (flag_n != flag_v);              // LT  signed <
            4'd12:   cond_met = !flag_z && (flag_n == flag_v);   // GT  signed >
            4'd13:   cond_met = flag_z || (flag_n != flag_v);    // LE  signed <=
            4'd14:   cond_met = 1'b1;                            // AL  always
            default: cond_met = 1'b0;                            // 15 reserved: never
        endcase
    end

    // ---- single register-write port and flag update, computed combinationally
    reg         wr_en, upd_zn, upd_c, upd_v;
    reg  [2:0]  wr_idx;
    reg  [15:0] wr_data, zn_val;
    always @* begin
        wr_en = 1'b0;  wr_idx = rd;  wr_data = alu_y;
        upd_zn = 1'b0; upd_c = 1'b0; upd_v = 1'b0; zn_val = alu_y;
        if (state == EXECUTE) begin
            case (opcode)
                OP_LDI: begin
                    wr_en = 1'b1; wr_data = operand;
                    upd_zn = 1'b1; zn_val = operand;
                end
                OP_ADD, OP_SUB, OP_ADDI: begin
                    wr_en = 1'b1; upd_zn = 1'b1; upd_c = 1'b1; upd_v = 1'b1;
                end
                OP_CMP: begin upd_zn = 1'b1; upd_c = 1'b1; upd_v = 1'b1; end
                OP_AND, OP_OR, OP_XOR, OP_MOV: begin wr_en = 1'b1; upd_zn = 1'b1; end
                OP_GRP0: case (func)
                    F_ADC, F_SBC: begin wr_en = 1'b1; upd_zn = 1'b1; upd_c = 1'b1; upd_v = 1'b1; end
                    F_NOT:        begin wr_en = 1'b1; upd_zn = 1'b1; end
                    F_SHL, F_SHR, F_SAR, F_RCR:
                                  begin wr_en = 1'b1; upd_zn = 1'b1; upd_c = 1'b1; end
                    F_PUSH, F_POP: begin wr_en = 1'b1; wr_idx = rs; wr_data = rs_step; end
                    F_JALR:       begin wr_en = 1'b1; wr_data = pc; end
                    default:      if (is_bcc && cond_met) begin wr_en = 1'b1; wr_data = pc; end
                endcase
                default: ;
            endcase
        end else if (state == MEMORY && dmem_ready && is_load) begin
            wr_en = 1'b1; wr_data = dmem_rdata;
            upd_zn = 1'b1; zn_val = dmem_rdata;
        end
    end

    // ---- external interfaces
    assign imem_addr  = pc;
    assign imem_valid = rst_n && !halted && (state == FETCH || state == EXTENSION);
    assign dmem_addr  = operand;           // absolute or pointer address, latched before MEMORY
    assign dmem_wdata = rd_value;
    assign dmem_valid = rst_n && !halted && (state == MEMORY);
    assign dmem_we    = dmem_valid && is_store;

    // Verification hook (not a port, removed by synthesis): high for the edge on which an
    // instruction completes. Used by tb/tb_cpu16.sv when compiled with +define+WHITEBOX.
    /* verilator lint_off UNUSEDSIGNAL */
    wire retire = rst_n && !halted &&
                  ((state == EXECUTE && opcode != OP_LD && opcode != OP_ST &&
                    !(grp0 && (func == F_LDX || func == F_STX || func == F_PUSH || func == F_POP))) ||
                   (state == MEMORY && dmem_ready));
    /* verilator lint_on UNUSEDSIGNAL */

    always @(posedge clk) begin
        if (!rst_n) begin
            state       <= FETCH;
            pc          <= 16'b0;
            operand     <= 16'b0;
            instruction <= 16'b0;
            flag_z <= 1'b0; flag_c <= 1'b0; flag_n <= 1'b0; flag_v <= 1'b0;
            halted      <= 1'b0;
            for (i = 1; i < 8; i = i + 1) regs[i] <= 16'b0;
        end else if (!halted) begin
            if (wr_en && wr_idx != 3'd0) regs[wr_idx] <= wr_data;
            if (upd_zn) begin flag_z <= (zn_val == 16'h0000); flag_n <= zn_val[15]; end
            if (upd_c)  flag_c <= alu_carry;
            if (upd_v)  flag_v <= alu_overflow;
            case (state)
                FETCH: if (imem_ready) begin
                    instruction <= imem_rdata;
                    operand     <= {8'b0, imem_rdata[7:0]};
                    if (!f_halt) pc <= pc + 16'd1;       // PC stays on the HALT word
                    state <= f_has_ext ? EXTENSION : EXECUTE;
                end
                EXTENSION: if (imem_ready) begin
                    operand <= imem_rdata;
                    pc      <= pc + 16'd1;
                    state   <= EXECUTE;
                end
                EXECUTE: begin
                    state <= FETCH;
                    case (opcode)
                        OP_LD, OP_ST: state <= MEMORY;
                        OP_JMP: pc <= operand;
                        OP_JZ:  if (flag_z)  pc <= operand;
                        OP_JNZ: if (!flag_z) pc <= operand;
                        OP_HALT: halted <= 1'b1;
                        OP_GRP0: case (func)
                            F_LDX, F_STX, F_POP: begin operand <= rs_value; state <= MEMORY; end
                            F_PUSH:              begin operand <= rs_step;  state <= MEMORY; end
                            F_JR, F_JALR:        pc <= rs_value;
                            default:             if (is_bcc && cond_met) pc <= operand;
                        endcase
                        default: ;
                    endcase
                end
                MEMORY: if (dmem_ready) state <= FETCH;
                default: state <= FETCH;
            endcase
        end
    end
endmodule
`default_nettype wire
