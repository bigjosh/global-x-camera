/* Fixed-address RAM for the host-only ADC register model. No device access. */
#ifndef ADC_MODEL_HOST_MEMORY_H
#define ADC_MODEL_HOST_MEMORY_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <stddef.h>
/* Avoid windows.h's register/type macros colliding with the CMSIS headers. */
__declspec(dllimport) void *__stdcall VirtualAlloc(void *, size_t, unsigned long, unsigned long);
static void model_map(uintptr_t base, size_t length)
{
  uintptr_t aligned = base & ~(uintptr_t)65535;
  size_t size = (length + base - aligned + 65535) & ~(size_t)65535;
  if (VirtualAlloc((void *)aligned, size, 0x3000, 4) != (void *)aligned) {
    fprintf(stderr, "Cannot reserve host model address %llx\n", (unsigned long long)base);
    exit(2);
  }
}
#else
#include <sys/mman.h>
static void model_map(uintptr_t base, size_t length)
{
  void *p = mmap((void *)base, length, PROT_READ | PROT_WRITE,
                 MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
  if (p != (void *)base) { perror("ADC model mmap"); exit(2); }
}
#endif
#endif
