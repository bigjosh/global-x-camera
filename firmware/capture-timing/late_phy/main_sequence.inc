  /* Matched follower control: both configurations keep all sensor settings
   * equal; only receiver initialization relative to START ACK differs. */
  volatile uint32_t *early_sensor=(volatile uint32_t *)0x343F4000U;
  if(early_sensor[0]!=0x53454E31U || early_sensor[1]!=37U || early_sensor[2]) fail(0x71,-1);
  if(early_sensor[28]!=2U || early_sensor[29] || early_sensor[30]!=0x1CU ||
     !(early_sensor[31]&RCC_APB5RSTR_CSIRST)) fail(0x95,-1);
  uint32_t sensor_start_end=early_sensor[5];
  TRACE[62]=(uint32_t)(DWT->CYCCNT-sensor_start_end); TRACE[63]=0;
  gpio.Pin=GPIO_PIN_0; gpio.Mode=GPIO_MODE_IT_RISING_FALLING; gpio.Pull=GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA,&gpio);
  __HAL_GPIO_EXTI_CLEAR_RISING_IT(GPIO_PIN_0); __HAL_GPIO_EXTI_CLEAR_FALLING_IT(GPIO_PIN_0);
  TRACE[35]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  if(TRACE[35]) fail(0x73,-1);
  HAL_NVIC_SetPriority(EXTI0_IRQn,3,0); HAL_NVIC_EnableIRQ(EXTI0_IRQn);
  TRACE[30]=2;
  if(!LATE_PHY_MODE) prepare_receiver();
  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();
  do { check(0x75,rd8(&sensor,0x0201,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x75,-100); } while(state);
  do { check(0x76,rd8(&sensor,0x0028,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x76,-100); } while(state!=3U);
  sensor.ctx.is_streaming=1; LATE[22]=DWT->CYCCNT;
  event(26); late_snapshot(307);
  if(LATE_PHY_MODE) prepare_receiver();
  qualify_stop();
  if(frames || vsyncs || HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0)) fail(0x96,-1);
  arm_receiver();
  early_sensor[16]=DWT->CYCCNT;
  TRACE[61]=(uint32_t)(early_sensor[16]-sensor_start_end);
  event(250); late_snapshot(310);
  if(LATE[3]) fail(0x94,-2);
  uint8_t fsync=0xFF;
  check(0x97,rd8(&sensor,0x0202,&fsync));
  if(fsync) fail(0x97,-1);
  LATE[23]=DWT->CYCCNT; event(152); late_snapshot(311);
  check(0x97,wr8(&sensor,0x0202,2));
  LATE[24]=DWT->CYCCNT; event(153); late_snapshot(312);
  TRACE[28]=TRACE[35]; TRACE[29]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
