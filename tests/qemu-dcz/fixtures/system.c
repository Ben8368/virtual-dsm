/* Generic AArch64 system-mode tests; no DSM or RTD1619B assumptions. */
#include <stdint.h>
#include <stddef.h>
static volatile uint32_t *const uart = (void *)0x09000000;
static unsigned failures;
volatile uintptr_t expected_resume;
volatile unsigned migration_go;
static volatile unsigned fault_count;
static volatile unsigned expected_ec, last_iss;
static uint64_t table[512] __attribute__((aligned(4096)));
static volatile unsigned secondary_ready, request, response, concurrent_calls, concurrent_error;
static unsigned char data[8192] __attribute__((aligned(4096)));
static uint32_t code[2048] __attribute__((aligned(4096)));
static uint32_t current[1024] __attribute__((aligned(4096)));
extern void invoke_expect_fault(void *fn);
extern void secondary_start(void);
__attribute__((noinline)) void watchpoint_marker(void) { asm volatile("nop" ::: "memory"); }
static void puts(const char *s) { while (*s) *uart = (unsigned char)*s++; }
static void number(unsigned n) {
    char buf[16]; unsigned i = 0;
    do { buf[i++] = '0' + n % 10; n /= 10; } while (n);
    while (i) *uart = buf[--i];
}
static void check(int ok, const char *name) {
    puts(ok ? "PASS " : "FAIL "); puts(name); puts("\n"); failures += !ok;
}
static void sync_code(void *p) {
    asm volatile("dc cvau, %0; dsb ish; ic ivau, %0; dsb ish; isb" :: "r"(p) : "memory");
}
static void zva(void *p) { asm volatile("dc zva, %0" :: "r"(p) : "memory"); }
static void barrier(void) { asm volatile("dsb ish; isb" ::: "memory"); }
static unsigned call(void *p) { return ((unsigned (*)(void))p)(); }
static void function(uint32_t *p, unsigned value) {
    p[0] = 0x52800000 | (value << 5); /* mov w0,#value */
    p[1] = 0xd65f03c0; /* ret */
    sync_code(p);
}
uintptr_t handle_exception(uint64_t esr, uintptr_t pc) {
    if ((esr >> 26) == expected_ec && expected_resume) {
        last_iss = esr & 0x1ffffff;
        fault_count++;
        uintptr_t resume = expected_resume;
        expected_resume = 0;
        return resume;
    }
    puts("FAIL unexpected exception ESR="); number(esr >> 26); puts("\n");
    failures++;
    for (;;) asm volatile("wfe");
    return pc;
}
static long cpu_on(void) {
    register uint64_t x0 asm("x0") = 0xc4000003;
    register uint64_t x1 asm("x1") = 1;
    register uint64_t x2 asm("x2") = (uintptr_t)secondary_start;
    register uint64_t x3 asm("x3") = 0;
    asm volatile("hvc #0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3) : "memory");
    return x0;
}
void secondary_main(void) {
    secondary_ready = 1;
    asm volatile("dmb ish; sev" ::: "memory");
    for (;;) {
        unsigned r = request;
        if (r && response != r) {
            /* CPU0 rewrites code only while CPU1 is between calls. */
            asm volatile("dmb ish; isb" ::: "memory");
            unsigned value = call(&code[32]);
            response = value == r ? r : 0xdead;
            asm volatile("dmb ish; sev" ::: "memory");
        } else {
            if (call(code + 64) != 99) concurrent_error = 1;
            concurrent_calls++;
            asm volatile("yield");
        }
    }
}
void main(void) {
#ifdef TEST_MIGRATION
    uint32_t random = 0x9e3779b9;
    for (uintptr_t p = 0x41000000; p < 0x42000000; p += 4) {
        random ^= random << 13; random ^= random >> 17; random ^= random << 5;
        *(volatile uint32_t *)p = random;
    }
    /* Keep translated code on each target page while migration clears its
     * dirty bitmap. The first block does not overlap this code, so the
     * candidate's conservative full-page path is exercised during migration. */
    for (uintptr_t p = 0x41000000; p < 0x42000000; p += 4096) {
        function((uint32_t *)(p + 128), 55);
        (void)call((void *)(p + 128));
    }
    puts("DCZ_MIGRATION_CODE_PAGES=4096\n");
    puts("DCZ_MIGRATION_READY\n");
    while (!migration_go) asm volatile("yield" ::: "memory");
    for (uintptr_t p = 0x41000000; p < 0x42000000; p += 64) zva((void *)p);
    asm volatile("dsb ish" ::: "memory");
    puts("DCZ_MIGRATION_CLEARED\n");
    for (;;) asm volatile("wfe");
#endif
    uint64_t dczid;
    asm volatile("mrs %0, dczid_el0" : "=r"(dczid));
    unsigned block = 4u << (dczid & 15);
    check(!(dczid & 16) && block == 64, "DCZID advertises 64 bytes");
    for (unsigned offset = 0; offset < 4096; offset += 64) {
        for (unsigned i = 0; i < sizeof(data); i++) data[i] = 0x5a;
        zva(data + offset + 17);
        for (unsigned i = 0; i < sizeof(data); i++) {
            if (data[i] != (i >= offset && i < offset + block ? 0 : 0x5a)) {
                failures++; break;
            }
        }
    }
    check(failures == 0, "RAM exact block and surrounding bytes at 64 alignments");
    function((uint32_t *)(data + 128), 55);
    check(call(data + 128) == 55, "watchpoint target page also contains translated code");
    watchpoint_marker();
    zva(data);
    check(call(data + 128) == 55, "watched code/data page unaffected code preserved");
    /* Build TB coverage throughout one RAM page, as allocator reuse can see. */
    for (unsigned i = 0; i < 64; i++) function(code + i * 16, i + 1);
    unsigned ok = 1;
    for (unsigned i = 0; i < 64; i++) ok &= call(code + i * 16) == i + 1;
    check(ok, "translated code spans all 64 blocks");
    puts("DCZ_CLEAR_BEGIN\n");
    for (unsigned i = 0; i < 64; i++) zva(code + i * 16);
    barrier();
    puts("DCZ_CLEAR_END\n");
    for (unsigned i = 0; i < 64; i++) function(code + i * 16, i + 1);
    for (unsigned i = 0; i < 64; i++) (void)call(code + i * 16);
    zva(code);
    barrier();
    check(call(code + 32) == 3, "unaffected same-page code retranslates safely");
    invoke_expect_fault(code);
    check(fault_count == 1, "zeroed translated code faults instead of stale execution");
    for (unsigned i = 1; i < 64; i++) zva(code + i * 16);
    barrier();
    for (unsigned i = 0; i < 1024; i++) ok &= code[i] == 0;
    check(ok, "full clear retains architectural 64-byte write semantics");
    /* Execute DC ZVA from the page containing the executing TB, then ISB.
     * The cleared block is separate from the still-executing instructions. */
    current[0] = 0xd50b7420; /* dc zva,x0 */
    current[1] = 0xd5033b9f; /* dsb ish */
    current[2] = 0xd5033fdf; /* isb (ends translated block) */
    current[3] = 0x528004e0; /* mov w0,#39 */
    current[4] = 0xd65f03c0;
    function(current + 16, 81);
    check(call(current + 16) == 81, "current-page target translated");
    sync_code(current);
    unsigned result = ((unsigned (*)(void *))current)(current + 16);
    check(result == 39, "current TB same-page ZVA continues correctly across ISB");
    invoke_expect_fault(current + 16);
    check(fault_count == 2, "current-page affected TB cannot execute stale code");
    /* Zero the currently executing instructions themselves. Arm does not use
     * TARGET_HAS_PRECISE_SMC: the existing ISB boundary must fetch fresh code. */
    current[0] = 0xd50b7420; /* dc zva,x0; wrapper passes function address in x0 */
    current[1] = 0xd5033b9f; /* dsb ish */
    current[2] = 0xd508751f; /* ic iallu */
    current[3] = 0xd5033b9f; /* dsb ish */
    current[4] = 0xd5033fdf; /* isb */
    current[5] = 0x528009a0; /* mov w0,#77: must not execute stale after ISB */
    current[6] = 0xd65f03c0;
    sync_code(current);
    invoke_expect_fault(current);
    check(fault_count == 3, "self-zeroing current TB refetches after ISB");
    /* AArch64 ends TBs at a guest page boundary. This function spans two
     * pages and thus two TBs; zero the page containing its return. */
    function(code + 1023, 67);
    check(call(code + 1023) == 67, "two-page function executes across separate TBs");
    zva(code + 1024);
    barrier();
    invoke_expect_fault(code + 1023);
    check(fault_count == 4, "two-page function cannot use stale second-page TB");
    function(code + 1023, 68);
    check(call(code + 1023) == 68, "two-page function safely retranslates");
    function(code + 64, 99);
    function(code + 32, 1);
    long on = cpu_on();
    check(on == 0, "PSCI starts second TCG vCPU");
    unsigned spins = 0;
    while (!secondary_ready && ++spins < 100000000) asm volatile("yield");
    check(secondary_ready, "second vCPU running");
    ok = 1;
    for (unsigned r = 1; r <= 128 && secondary_ready; r++) {
        request = 0;
        asm volatile("dmb ish" ::: "memory");
        zva(code); /* invalidates a page with CPU1's unaffected TB */
        function(code + 32, r);
        request = r;
        asm volatile("dmb ish; sev" ::: "memory");
        spins = 0;
        while (response != r && response != 0xdead && ++spins < 100000000) asm volatile("yield");
        if (response != r) { ok = 0; break; }
    }
    check(ok && secondary_ready && !concurrent_error && concurrent_calls,
          "128 two-vCPU SMC handoffs and concurrent same-page TB execution");
    /* Identity map RAM and devices, plus a read-only alias of RAM. */
    table[0] = (1ull << 10) | 1; /* 1GiB Device, AF */
    table[1] = 0x40000000ull | (1ull << 10) | (3ull << 8) | (1ull << 2) | 1;
    table[2] = 0x40000000ull | (1ull << 10) | (3ull << 8) | (1ull << 2) | (2ull << 6) | 1;
    uint64_t tcr = 25 | (1ull << 8) | (1ull << 10) | (3ull << 12) | (2ull << 32);
    uint64_t mair = 0xff04;
    asm volatile("dsb sy; msr mair_el1,%0; msr tcr_el1,%1; msr ttbr0_el1,%2; isb"
                 :: "r"(mair), "r"(tcr), "r"((uintptr_t)table) : "memory");
    uint64_t sctlr;
    asm volatile("mrs %0,sctlr_el1" : "=r"(sctlr));
    sctlr |= 1 | (1 << 2) | (1 << 12);
    asm volatile("msr sctlr_el1,%0; isb" :: "r"(sctlr) : "memory");
    zva(data);
    check(data[0] == 0, "DC ZVA with MMU enabled");
    /* Function wrappers below preserve expected exception return state. */
    expected_ec = 0x25;
    unsigned before = fault_count;
    extern void readonly_zva(void), unmapped_zva(void);
    invoke_expect_fault(readonly_zva);
    check(fault_count == before + 1 && (last_iss & 0x3f) == 0x0d,
          "write-protected RAM alias raises permission fault");
    invoke_expect_fault(unmapped_zva);
    check(fault_count == before + 2 && (last_iss & 0x3f) == 0x05,
          "unmapped DC ZVA raises translation fault");
    /* PL011 ID registers ignore writes; their values must survive byte fallback. */
    uint32_t id = uart[0xfe0 / 4];
    zva((void *)0x09000fe0);
    check(uart[0xfe0 / 4] == id, "MMIO read-only ID registers retain byte-store behavior");
    puts("DCZ_TEST_RESULT failures="); number(failures); puts("\n");
    /* Arm semihosting SYS_EXIT_EXTENDED. */
    uint64_t exit_args[2] = {0x20026, failures ? 1 : 0};
    register uint64_t x0 asm("x0") = 0x20;
    register void *x1 asm("x1") = exit_args;
    asm volatile("hlt #0xf000" : : "r"(x0), "r"(x1) : "memory");
    for (;;) asm volatile("wfe");
}
