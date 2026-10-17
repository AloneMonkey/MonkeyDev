#include <capstone/capstone.h>
#include <keystone/keystone.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    ks_engine *assembler = NULL;
    unsigned char *bytes = NULL;
    size_t size = 0, statements = 0;
    const unsigned char expected[] = {0xe0, 0x03, 0x01, 0xaa};
    if (ks_open(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, &assembler) != KS_ERR_OK)
        return 1;
    if (ks_asm(assembler, "mov x0, x1", 0, &bytes, &size, &statements) != KS_ERR_OK)
        return 2;
    if (size != sizeof(expected) || memcmp(bytes, expected, size) != 0 || statements != 1)
        return 3;

    csh decoder;
    if (cs_open(CS_ARCH_AARCH64, CS_MODE_LITTLE_ENDIAN, &decoder) != CS_ERR_OK)
        return 4;
    cs_insn *instructions = NULL;
    size_t count = cs_disasm(decoder, bytes, size, 0x1000, 0, &instructions);
    if (count != 1 || strcmp(instructions[0].mnemonic, "mov") != 0 ||
        strcmp(instructions[0].op_str, "x0, x1") != 0)
        return 5;
    printf("Keystone -> e00301aa -> Capstone: %s %s\n",
           instructions[0].mnemonic, instructions[0].op_str);
    cs_free(instructions, count);
    cs_close(&decoder);
    ks_free(bytes);
    ks_close(assembler);
    return 0;
}
