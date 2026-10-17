/*
 * Copyright (c) 2023-2024 STMicroelectronics. All rights reserved.
 * Adapted from x-cube-n6-camera-capture Src/app.c and Src/app_cam.c.
 * Licensed under ST-LICENSE.md (SLA0044); bring-up modifications October 2026.
 * Build this instead of both app.c and app_cam.c. Enable USE_VD56G3_SENSOR.
 * main.c supplies clocks, UART/printf at 115200, interrupts and RAM security.
 * No USB protocol, NAND/NOR writes, OTP writes or production timing claims.
 */
#include "app.h"
#include "app_cam.h"
#include "cmw_camera.h"
#include "stm32n6xx_hal.h"
#include "utils.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CAPTURE_WIDTH       640U
#define CAPTURE_HEIGHT      480U
#define CAPTURE_BYTES       (CAPTURE_WIDTH * CAPTURE_HEIGHT)
#define SETTLING_FRAMES     3U
#define CAPTURE_TIMEOUT_MS  10000U

/* The Nucleo linker script maps .psram_bss to internal AXI SRAM 0x34000000. */
uint8_t g_capture_frame[CAPTURE_BYTES] ALIGN_32 IN_PSRAM;
volatile uint32_t g_capture_ready;
volatile uint32_t g_capture_stage;
volatile uint32_t g_frame_count;
volatile uint32_t g_vsync_count;
volatile uint32_t g_pipe_error_count;
volatile uint32_t g_dcmipp_error_count;
volatile uint32_t g_csi_line_error_count;
volatile uint32_t g_dcmipp_error_flags;
volatile uint32_t g_final_frame_errors;
volatile int32_t g_capture_result;
volatile uint32_t g_capture_min;
volatile uint32_t g_capture_max;
volatile uint32_t g_capture_sum;
volatile uint32_t g_capture_hash;
volatile uint32_t g_capture_elapsed_ms;

/* Set to 1 at app_run's debugger breakpoint, after startup clears BSS.
 * Default zero preserves the camera capture path and leaves these pins alone. */
volatile uint32_t g_probe_smoke_mode;
volatile uint32_t g_probe_smoke_done;

__attribute__((noinline)) void probe_smoke_complete(void)
{
  while (1) {
    HAL_Delay(100);
  }
}

static void probe_smoke_run(void)
{
  GPIO_InitTypeDef gpio = {0};
  uint32_t i;

  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_0, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOE, GPIO_PIN_0, GPIO_PIN_RESET);
  gpio.Pin = GPIO_PIN_0;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOD, &gpio);  /* CN15 pin 33, Saleae CH1. */
  HAL_GPIO_Init(GPIOE, &gpio);  /* CN15 pin 29, Saleae CH2. */

  HAL_Delay(100);
  for (i = 0; i < 4; i++) {
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_0, GPIO_PIN_SET);
    HAL_Delay(50);
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_0, GPIO_PIN_RESET);
    HAL_Delay(50);
  }
  HAL_Delay(100);
  for (i = 0; i < 3; i++) {
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_0, GPIO_PIN_SET);
    HAL_Delay(100);
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_0, GPIO_PIN_RESET);
    HAL_Delay(100);
  }
  HAL_Delay(100);
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_0, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOE, GPIO_PIN_0, GPIO_PIN_SET);
  HAL_Delay(200);
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_0, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOE, GPIO_PIN_0, GPIO_PIN_RESET);
  HAL_Delay(100);
  g_probe_smoke_done = 1;
  probe_smoke_complete();
}

/* Named breakpoint survives edits above the buffer-frozen success loop. */
__attribute__((noinline)) void capture_complete(void)
{
  while (1) {
    HAL_Delay(100);
  }
}

static void capture_fail(const char *where, int32_t result)
{
  g_capture_result = result;
  g_capture_stage = 0xFFFFFFFFU;
  g_capture_ready = 0;
  printf("CAPTURE FAIL: %s ret=%ld frames=%lu vsync=%lu flags=0x%08lx\r\n",
         where, (long)result, (unsigned long)g_frame_count,
         (unsigned long)g_vsync_count, (unsigned long)g_dcmipp_error_flags);
  /* Keep all diagnostics available to the debugger; do not reset the board. */
  while (1) {
    HAL_Delay(100);
  }
}

static void check_result(const char *where, int32_t result)
{
  if (result != CMW_ERROR_NONE)
    capture_fail(where, result);
}

void CAM_Init(CAM_conf_t *conf)
{
  CMW_Sensor_Name_t sensor = CMW_UNKNOWN_Sensor;
  CMW_CameraInit_t camera = {0};
  CMW_DCMIPP_Conf_t pipe = {0};
  uint32_t pitch = 0;
  float ratio_x;
  float ratio_y;
  float ratio;

  check_result("GetSensorName", CMW_CAMERA_GetSensorName(&sensor));
  printf("Detected sensor enum=%d (VD56G3=%d)\r\n", (int)sensor, (int)CMW_VD56G3_Sensor);
  if (sensor != CMW_VD56G3_Sensor)
    capture_fail("Expected VD56G3", CMW_ERROR_WRONG_PARAM);

  /* 0x0 asks the middleware for the full native sensor mode. */
  camera.width = 0;
  camera.height = 0;
  camera.fps = conf->fps;
  camera.mirror_flip = CMW_MIRRORFLIP_NONE;
  check_result("CMW_CAMERA_Init", CMW_CAMERA_Init(&camera, NULL));
  if (camera.width == 0 || camera.height == 0)
    capture_fail("Zero sensor dimensions", CMW_ERROR_WRONG_PARAM);
  printf("Sensor initialized: %lux%lu, %d fps\r\n",
         (unsigned long)camera.width, (unsigned long)camera.height, camera.fps);

  /* Match the official app's aspect-preserving centered crop and scaling. */
  ratio_x = (float)camera.width / (float)conf->capture_width;
  ratio_y = (float)camera.height / (float)conf->capture_height;
  ratio = MIN(ratio_x, ratio_y);
  if (ratio < 1.0f || ratio >= 64.0f)
    capture_fail("Unsupported crop ratio", CMW_ERROR_WRONG_PARAM);

  pipe.output_width = conf->capture_width;
  pipe.output_height = conf->capture_height;
  pipe.output_format = conf->dcmipp_output_format;
  pipe.output_bpp = 1;
  pipe.mode = CMW_Aspect_ratio_manual_roi;
  pipe.enable_swap = conf->is_rgb_swap;
  pipe.enable_gamma_conversion = 0;
  pipe.manual_conf.width = (uint32_t)MIN(conf->capture_width * ratio, camera.width);
  pipe.manual_conf.height = (uint32_t)MIN(conf->capture_height * ratio, camera.height);
  pipe.manual_conf.offset_x = (camera.width - pipe.manual_conf.width + 1U) / 2U;
  pipe.manual_conf.offset_y = (camera.height - pipe.manual_conf.height + 1U) / 2U;
  check_result("SetPipeConfig", CMW_CAMERA_SetPipeConfig(DCMIPP_PIPE1, &pipe, &pitch));
  if (pitch != CAPTURE_WIDTH)
    capture_fail("Unexpected Y8 pitch", CMW_ERROR_WRONG_PARAM);
  printf("Pipe1 ready: %lux%lu MONO_Y8, pitch=%lu\r\n",
         (unsigned long)pipe.output_width, (unsigned long)pipe.output_height,
         (unsigned long)pitch);
}

void CAM_CapturePipe_Start(uint8_t *destination, uint32_t mode)
{
  check_result("CMW_CAMERA_Start", CMW_CAMERA_Start(DCMIPP_PIPE1, destination, mode));
}

void CAM_IspUpdate(void)
{
  check_result("CMW_CAMERA_Run", CMW_CAMERA_Run());
}

void CAM_Deinit(void)
{
  check_result("CMW_CAMERA_DeInit", CMW_CAMERA_DeInit());
}

static void stop_pipe(void)
{
  HAL_StatusTypeDef result = HAL_DCMIPP_CSI_PIPE_Stop(CMW_CAMERA_GetDCMIPPHandle(),
                                                    DCMIPP_PIPE1, DCMIPP_VIRTUAL_CHANNEL0);
  if (result != HAL_OK)
    capture_fail("HAL_DCMIPP_CSI_PIPE_Stop", (int32_t)result);
}

static void wait_for_frame_count(uint32_t target)
{
  uint32_t start = HAL_GetTick();
  uint32_t processed_vsync = g_vsync_count;
  uint32_t last_report = start;

  while (g_frame_count < target) {
    uint32_t now = HAL_GetTick();
    uint32_t vsync = g_vsync_count;
    if (vsync != processed_vsync) {
      processed_vsync = vsync;
      /* Same deferred ISP update as the official app; no I2C from interrupts. */
      CAM_IspUpdate();
    }
    g_dcmipp_error_flags |= CMW_CAMERA_GetDCMIPPHandle()->ErrorCode;
    if (now - start >= CAPTURE_TIMEOUT_MS) {
      stop_pipe();
      capture_fail("Frame timeout", -100);
    }
    if (now - last_report >= 1000U) {
      last_report = now;
      printf("Waiting: frames=%lu vsync=%lu errors=0x%08lx\r\n",
             (unsigned long)g_frame_count, (unsigned long)g_vsync_count,
             (unsigned long)g_dcmipp_error_flags);
    }
    HAL_Delay(1);
  }
}

int CMW_CAMERA_PIPE_FrameEventCallback(uint32_t pipe)
{
  if (pipe == DCMIPP_PIPE1)
    g_frame_count++;
  return CMW_ERROR_NONE;
}

int CMW_CAMERA_PIPE_VsyncEventCallback(uint32_t pipe)
{
  if (pipe == DCMIPP_PIPE1)
    g_vsync_count++;
  return CMW_ERROR_NONE;
}

void CMW_CAMERA_PIPE_ErrorCallback(uint32_t pipe)
{
  (void)pipe;
  g_pipe_error_count++;
  g_dcmipp_error_flags |= CMW_CAMERA_GetDCMIPPHandle()->ErrorCode;
}

void HAL_DCMIPP_ErrorCallback(DCMIPP_HandleTypeDef *handle)
{
  g_dcmipp_error_count++;
  g_dcmipp_error_flags |= handle->ErrorCode;
}

void HAL_DCMIPP_CSI_LineErrorCallback(DCMIPP_HandleTypeDef *handle, uint32_t lane)
{
  (void)lane;
  g_csi_line_error_count++;
  g_dcmipp_error_flags |= handle->ErrorCode;
}

void app_run(void)
{
  if (g_probe_smoke_mode == 1U)
    probe_smoke_run();

  CAM_conf_t config = {
    .capture_width = CAPTURE_WIDTH,
    .capture_height = CAPTURE_HEIGHT,
    .fps = 30,
    .dcmipp_output_format = DCMIPP_PIXEL_PACKER_FORMAT_MONO_Y8_G8_1,
    .is_rgb_swap = 0,
  };
  uint32_t start = HAL_GetTick();
  uint32_t final_target;
  uint32_t errors_before_final;
  uint32_t minimum = 255;
  uint32_t maximum = 0;
  uint32_t sum = 0;
  uint32_t hash = 2166136261U;
  uint32_t i;

  g_capture_ready = 0;
  g_capture_stage = 1;
  g_capture_result = 0;
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  printf("\r\nGlobal X RAM-only camera capture: 640x480 Y8\r\n");
  printf("Frame buffer 0x%08lx, %lu bytes; UART 115200\r\n",
         (unsigned long)(uintptr_t)g_capture_frame, (unsigned long)sizeof(g_capture_frame));

  memset(g_capture_frame, 0xA5, sizeof(g_capture_frame));
  if ((SCB->CCR & SCB_CCR_DC_Msk) != 0U)
    SCB_CleanInvalidateDCache_by_Addr(g_capture_frame, sizeof(g_capture_frame));
  __DSB();
  CAM_Init(&config);

  /* CMW uses microseconds for exposure and millidecibels for total gain.
   * 0 mdB selects unity analog and digital gain in its VD56G3 driver. */
  check_result("Manual exposure", CMW_CAMERA_SetExposureMode(CMW_EXPOSUREMODE_MANUAL));
  check_result("10 ms exposure", CMW_CAMERA_SetExposure(10000));
  check_result("Unity gain", CMW_CAMERA_SetGain(0));
  printf("Manual exposure 10000 us, gain 0 mdB (unity)\r\n");
  g_capture_stage = 2;
  printf("Streaming %lu settling frames...\r\n", (unsigned long)SETTLING_FRAMES);
  CAM_CapturePipe_Start(g_capture_frame, CMW_MODE_CONTINUOUS);
  wait_for_frame_count(SETTLING_FRAMES);

  /* Stop the continuous receiver, then capture one complete hardware snapshot.
   * Merely stopping continuous DMA could leave a partially overwritten frame.
   * The sensor remains streaming, so its settings have time to take effect. */
  g_capture_stage = 3;
  stop_pipe();
  final_target = g_frame_count + 1U;
  errors_before_final = g_pipe_error_count + g_dcmipp_error_count + g_csi_line_error_count;
  g_capture_stage = 4;
  printf("Capturing final snapshot...\r\n");
  CAM_CapturePipe_Start(g_capture_frame, CMW_MODE_SNAPSHOT);
  wait_for_frame_count(final_target);
  stop_pipe();
  g_final_frame_errors = g_pipe_error_count + g_dcmipp_error_count +
                         g_csi_line_error_count - errors_before_final;

  /* DMA writes bypass the CPU D-cache. Invalidate before inspecting pixels. */
  __DSB();
  if ((SCB->CCR & SCB_CCR_DC_Msk) != 0U)
    SCB_InvalidateDCache_by_Addr(g_capture_frame, sizeof(g_capture_frame));
  __DSB();
  for (i = 0; i < sizeof(g_capture_frame); i++) {
    uint32_t value = g_capture_frame[i];
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
    sum += value;
    hash = (hash ^ value) * 16777619U;
  }
  g_capture_min = minimum;
  g_capture_max = maximum;
  g_capture_sum = sum;
  g_capture_hash = hash;
  g_capture_elapsed_ms = HAL_GetTick() - start;
  g_dcmipp_error_flags |= CMW_CAMERA_GetDCMIPPHandle()->ErrorCode;
  g_capture_stage = 5;
  __DMB();
  g_capture_ready = 1;
  printf("CAPTURE READY buffer=0x%08lx bytes=%lu frames=%lu vsync=%lu ms=%lu\r\n",
         (unsigned long)(uintptr_t)g_capture_frame, (unsigned long)sizeof(g_capture_frame),
         (unsigned long)g_frame_count, (unsigned long)g_vsync_count,
         (unsigned long)g_capture_elapsed_ms);
  printf("Pixels min=%lu max=%lu sum=%lu fnv1a=0x%08lx\r\n",
         (unsigned long)minimum, (unsigned long)maximum, (unsigned long)sum, (unsigned long)hash);
  printf("Errors pipe=%lu global=%lu CSI=%lu final=%lu flags=0x%08lx\r\n",
         (unsigned long)g_pipe_error_count, (unsigned long)g_dcmipp_error_count,
         (unsigned long)g_csi_line_error_count, (unsigned long)g_final_frame_errors,
         (unsigned long)g_dcmipp_error_flags);
  printf("Buffer frozen. Read g_capture_frame from debugger as 640x480 grayscale.\r\n");
  /* Do not touch the frozen buffer while the host retrieves it via ST-LINK. */
  capture_complete();
}
