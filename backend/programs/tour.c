// A tour of RV32I: every instruction the core has runs at least once.
// 'volatile' makes each read a real load, so the compiler cannot fold
// the answers in advance.
volatile int word = -8;                  // lw, sw
volatile short half = -2;                // lh, sh
volatile unsigned short uhalf = 65534;   // lhu
volatile signed char byte = -3;          // lb, sb
volatile unsigned char ubyte = 253;      // lbu
volatile int big = 0x12345;              // lui (constants over 12 bits)
short halves[2] = {7, -2};               // lh (an indexed read, not volatile)
signed char bytes[2] = {5, -3};          // lb

int smaller(int a, int b) {              // a call (jal) and a return (jalr)
    if (a < b)                           // blt or bge
        return a;
    return b;
}

int main(void) {
    int s = word;
    unsigned u = (unsigned)s;
    int k = ubyte & 1;                   // 1, known only at run time
    int h = halves[k];                   // -2
    int c = bytes[k];                    // -3
    int r = 0;

    r += s >> 1;                         // srai: -4
    r += (int)(u >> 28);                 // srli: 15
    r += s << 2;                         // slli: -32
    r += s >> (h + 3);                   // sra:  -8 >> 1 = -4
    r += (int)(u >> (c + 31));           // srl:  u >> 28 = 15
    r += 1 << (c + 5);                   // sll:  4
    r += s < h;                          // slt:  -8 < -2 is 1
    r += u < (unsigned)uhalf;            // sltu: 0xfffffff8 < 65534 is 0
    r += s < 5;                          // slti: 1
    r += u < 10u;                        // sltiu: 0
    r += (s ^ h) + (s ^ 0x55);           // xor, xori
    r += (s | ubyte) + (s | 0x70);       // or, ori
    r += (s & ubyte) + (s & 0x0f);       // and, andi
    r += big - ubyte;                    // sub

    unsigned a = uhalf, b = ubyte;
    if (a < b)                           // bltu or bgeu
        r += 100;
    if (b >= a)
        r += 200;
    if (h == c)                          // beq or bne
        r += 300;
    if (h != c + 1)
        r += 400;
    for (int i = c; i != 0; i++)         // bne: the loop goes back while i != 0
        r += i;                          // -3, -2, -1

    word = r;                            // sw
    half = (short)r;                     // sh
    byte = (signed char)r;               // sb
    return r + smaller(h, c) + word + half + byte;   // expected: 157845 in a0
}
