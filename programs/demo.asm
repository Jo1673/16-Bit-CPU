; Full-width addition, memory at 0x8000, comparison, and a countdown loop.
LDI R1, 0x1234
LDI R2, 0x0102
ADD R1, R2                 ; R1 = 0x1336
ST R1, [0x8000]
LD R3, [0x8000]
CMP R1, R3
JNZ fail
LDI R4, 5
loop:
ADDI R4, -1
JNZ loop
LDI R5, 0xbeef
ST R5, [0x8001]
HALT
fail:
LDI R5, 0xdead
ST R5, [0x8001]
HALT
