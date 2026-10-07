`timescale 1ns/1ps
// Port-only test works on RTL or the generic synthesized netlist.
module tb_gate;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire [15:0] ia,da,wd;
    wire iv,dv,we,halted;
    reg ready=0;
    reg [15:0] imem[0:65535],dmem[0:65535];
    integer i,cycles=0,writes=0;
    cpu16_core dut(.clk(clk),.rst_n(rst_n),.imem_addr(ia),.imem_valid(iv),
        .imem_rdata(imem[ia]),.imem_ready(ready),.dmem_addr(da),.dmem_wdata(wd),
        .dmem_valid(dv),.dmem_we(we),.dmem_rdata(dmem[da]),.dmem_ready(ready),.halted(halted));
    always @(negedge clk) ready=~ready;
    always @(posedge clk) begin
        cycles=cycles+1;
        if(dv && ready && we) begin dmem[da]<=wd; writes=writes+1; end
        if(cycles>1000) $fatal(1,"gate smoke timeout");
    end
    initial begin
        for(i=0;i<65536;i=i+1) begin imem[i]=0; dmem[i]=0; end
        $readmemh("build/demo.hex",imem);
        repeat(3) @(negedge clk);
        rst_n=1;
        wait(halted); #1;
        if(dmem[16'h8000]!==16'h1336 || dmem[16'h8001]!==16'hbeef || writes!=2)
            $fatal(1,"gate demo result mismatch");
        if(iv || dv || we) $fatal(1,"gate halt not quiescent");
        $display("PASS: synthesized port-only demo with wait states; 8000=1336, 8001=beef, exactly 2 stores");
        $finish;
    end
endmodule
