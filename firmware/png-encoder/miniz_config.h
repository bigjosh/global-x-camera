#ifndef PNG16_MINIZ_CONFIG_H
#define PNG16_MINIZ_CONFIG_H
/* Must precede every miniz include. Low-level tdefl never allocates. */
#define MINIZ_NO_STDIO
#define MINIZ_NO_TIME
#define MINIZ_NO_ARCHIVE_APIS
#define MINIZ_NO_ARCHIVE_WRITING_APIS
#define MINIZ_NO_ZLIB_APIS
#define MINIZ_NO_ZLIB_COMPATIBLE_NAMES
#define MINIZ_NO_INFLATE_APIS
#define MINIZ_NO_MALLOC
#define TDEFL_LESS_MEMORY 1
/* Cortex-M55 memory may have stricter alignment than a desktop. */
#define MINIZ_USE_UNALIGNED_LOADS_AND_STORES 0
#define MINIZ_LITTLE_ENDIAN 1
#ifndef NDEBUG
#define NDEBUG
#endif
#endif
