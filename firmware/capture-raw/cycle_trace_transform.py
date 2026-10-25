"""Optional fixed-store markers in the generated receiver, never the ROM prefix."""

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Cycle trace anchor differs: '+old[:100])
    return text.replace(old,new,1)

def transform(text):
    text=once(text,'#include "runtime.h"','#include "runtime.h"\n#include "cycle_trace.h"')
    pairs=[
        ('  HAL_Init();','  CYCLE_MARK(HAL_BEGIN);\n  HAL_Init();\n  CYCLE_MARK(HAL_DONE);'),
        ('  check(5, BSP_I2C2_Init());','  CYCLE_MARK(I2C_BEGIN);\n  check(5, BSP_I2C2_Init());\n  CYCLE_MARK(I2C_DONE);'),
        ('  prepare_receiver();','  CYCLE_MARK(RECEIVER_PREPARE_BEGIN);\n  prepare_receiver();\n  CYCLE_MARK(RECEIVER_PREPARE_DONE);'),
        ('  fast_streaming_data_enable();','  CYCLE_MARK(PHY_ENABLE_BEGIN);\n  fast_streaming_data_enable();'),
        ('  fast_qualify_stop();','  CYCLE_MARK(PHY_STOP_QUALIFY_BEGIN);\n  fast_qualify_stop();\n  CYCLE_MARK(PHY_STOP_QUALIFY_DONE);'),
        ('  arm_receiver();','  CYCLE_MARK(RECEIVER_ARM_BEGIN);\n  arm_receiver();\n  CYCLE_MARK(RECEIVER_ARM_DONE);'),
        ('  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();','  CYCLE_MARK(START_ACK_BEGIN);\n  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();'),
        ('do { check(0x75,','do { CYCLE_COUNT(START_ACK_READS); check(0x75,'),
        ('  FAST[9]=DWT->CYCCNT;','  CYCLE_MARK(START_ACK_DONE);\n  FAST[9]=DWT->CYCCNT;'),
        ('do { check(0x76,','do { CYCLE_COUNT(STREAMING_STATE_READS); check(0x76,'),
        ('  sensor.ctx.is_streaming=1;','  CYCLE_MARK(STREAMING_OBSERVED);\n  sensor.ctx.is_streaming=1;'),
        ('    frames++;','    CYCLE_MARK(FRAME_IRQ);\n    frames++;'),
        ('    capture_stop_poll=now;','    capture_stop_poll=now;\n    CYCLE_COUNT(SENSOR_STOP_POLLS);'),
        ('    raw_capture_stopped(); return;','    CYCLE_MARK(SENSOR_STOP_ACK_DONE);\n    raw_capture_stopped(); return;'),
        ('  capture_finalizing=1U;','  CYCLE_MARK(FRAME_CHECK_BEGIN);\n  capture_finalizing=1U;'),
        ('  CPROF[CP_FLAGS]=CP_F_GEOMETRY|CP_F_CANARY;','  CPROF[CP_FLAGS]=CP_F_GEOMETRY|CP_F_CANARY;\n  CYCLE_MARK(FRAME_GEOMETRY_DONE);'),
        ('  CPROF[CP_ESSENTIAL_DONE]=DWT->CYCCNT;','  CPROF[CP_ESSENTIAL_DONE]=DWT->CYCCNT;\n  CYCLE_MARK(FRAME_SENSOR_READS_DONE);'),
        ('  fast_snapshot(435); CPROF[CP_PIPE_STOP_BEGIN]=DWT->CYCCNT;','  CYCLE_MARK(PIPE_STOP_BEGIN);\n  fast_snapshot(435); CPROF[CP_PIPE_STOP_BEGIN]=DWT->CYCCNT;'),
        ('  CPROF[CP_PIPE_STOP_DONE]=DWT->CYCCNT; fast_snapshot(439);','  CPROF[CP_PIPE_STOP_DONE]=DWT->CYCCNT; fast_snapshot(439);\n  CYCLE_MARK(PIPE_STOP_DONE);'),
        ('  CPROF[CP_DATA_OFF_DONE]=DWT->CYCCNT;','  CPROF[CP_DATA_OFF_DONE]=DWT->CYCCNT;\n  CYCLE_MARK(DATA_LANES_OFF);'),
        ('  MAGIC_CHECK(33,wr8(&sensor,0x0202,1U));','  CYCLE_MARK(SENSOR_STOP_COMMAND_BEGIN);\n  MAGIC_CHECK(33,wr8(&sensor,0x0202,1U));\n  CYCLE_MARK(SENSOR_STOP_COMMAND_DONE);'),
        ('  capture_ready=1U; __DSB();','  capture_ready=1U; __DSB();\n  CYCLE_MARK(FRAME_VALIDATED);'),
    ]
    for old,new in pairs: text=once(text,old,new)
    return text
