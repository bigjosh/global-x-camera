/* One configuration for checksums and the low-level streaming compressor.
 * Compile with function/data sections and link with --gc-sections so upstream
 * convenience PNG/heap APIs that we do not call are discarded.
 */
#include "miniz_config.h"
#include "vendor/miniz/miniz.c"
#include "vendor/miniz/miniz_tdef.c"
