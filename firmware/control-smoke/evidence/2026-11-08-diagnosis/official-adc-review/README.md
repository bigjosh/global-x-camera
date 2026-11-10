## <b>ADC_MultiChannelSingleConversion Example Description</b>

How to use an ADC peripheral to convert several channels. ADC conversions are 
performed successively in a scan sequence.
This example is based on the STM32N6xx ADC HAL API.

Example configuration:

ADC is configured in single conversion mode, from SW trigger.
Sequencer of ADC group regular (default group available on ADC of all STM32 devices)
is configured to convert 2 channels: 1 channel from GPIO, 1 internal channel:
internal voltage reference VrefInt.
DMA is configured to transfer conversion data in an array of size three elements
(one array address for conversion data of each channel) in RAM memory,
in circular mode.

Example execution:

Every second, ADC performs conversion of a channel among the 2 channels
of the scan sequence, successively at each conversion start (discontinuous mode enabled).

Note: In case of discontinuous mode is disabled, then the entire scan sequence
      is converted in burst from one conversion start.

ADC conversion data of each sequence rank is transferred by DMA into the array
"uhADCxConvertedData":

- uhADCxConvertedData[0]: ADC channel set on sequence rank 1 (GPIO as analog input)
- uhADCxConvertedData[1]: ADC channel set on sequence rank 2 (VrefInt)

When sequence is completed, it restarts from the beginning: first channel 
in the sequence, data transfer in first array address (rollback).

ADC conversions raw data are computed to physical values
using LL ADC driver helper macro:

- Value of voltage on GPIO pin (on which is mapped ADC channel, cf pin below) (unit: mV)
- Value of internal voltage reference VrefInt (unit: mV)

Note: For this example purpose, analog reference voltage (Vref+) is computed
      from ADC conversion of internal voltage reference VrefInt and used
      to compute other conversion data.
      This voltage should correspond to value of literal "VDDA_APPLI".
      This procedure can be performed when value of voltage Vref+
      is unknown in the application.
      (This is not the case in this example due to target board
      supplied by a LDO regulator providing a known constant voltage
      of value "VDDA_APPLI").
      In typical case of Vref+ connected to Vdd, it allows to
      deduce Vdd value.

LED1 is used to monitor program execution status:

- Normal operation: Activity of ADC scan sequence
  can be observed with LED toggle:
  - At each ADC conversion: LED toggle once (every 1sec)
  - At each scan conversion completed: LED toggle 4 times quickly (10Hz)
- Error: LED remaining turned on

Debug: variables to monitor with debugger:

- "ubDmaTransferStatus": status of DMA transfer of ADC group regular conversions
- "uhADCxConvertedData":                          ADC group regular conversion data
- "uhADCxConvertedData_VoltageGPIO_mVolt":        Value of voltage on GPIO pin (on which is mapped ADC channel) (unit: mV)
- "uhADCxConvertedData_VrefInt_mVolt":            Value of internal voltage reference VrefInt (unit: mV)

Connection needed:

Use an external power supply to generate a voltage in range [0V; 1.8V]
and connect it to analog input pin (cf pin below).
Note: If no power supply available, this pin can be let floating (in this case
      ADC conversion data will be undetermined).

Other peripherals used:

  1 GPIO for LED1

  1 GPIO for analog input: ADC channel 4 on pin PA.01 (Morpho connector CN15 pin 38)

  1 DMA channel

### <b>Keywords</b>

ADC, analog digital converter, analog, conversion, voltage, channel, analog input, DMA transfer, sequence, temperature sensor, internal voltage reference, VrefInt, discontinuous

### <b>Directory contents</b>

  - ADC/ADC_MultiChannelSingleConversion/FSBL/Inc/stm32n6xx_nucleo_conf.h     BSP configuration file
  - ADC/ADC_MultiChannelSingleConversion/FSBL/Inc/stm32n6xx_hal_conf.h        HAL configuration file
  - ADC/ADC_MultiChannelSingleConversion/FSBL/Inc/stm32n6xx_it.h              Interrupt handlers header file
  - ADC/ADC_MultiChannelSingleConversion/FSBL/Inc/main.h                      Header for main.c module
  - ADC/ADC_MultiChannelSingleConversion/FSBL/Src/stm32n6xx_it.c              Interrupt handlers
  - ADC/ADC_MultiChannelSingleConversion/FSBL/Src/stm32n6xx_hal_msp.c         HAL MSP module
  - ADC/ADC_MultiChannelSingleConversion/FSBL/Src/main.c                      Main program
  - ADC/ADC_MultiChannelSingleConversion/FSBL/Src/system_stm32n6xx.c          STM32N6xx system source file

### <b>Hardware and Software environment</b>

  - This example runs on STM32N657X0HxQ devices.

  - This example has been tested with NUCLEO-N657X0-Q board and can be
    easily tailored to any other supported device and development board.

  - **EWARM** : To monitor a variable in the live watch window, you must proceed as follow :
    - Start a debugging session.
    - Open the View > Images.
    - Double-click to deselect the second instance of project.out.

  - **MDK-ARM** : To monitor a variable in the live watch window, you must comment out SCB_EnableDCache() in main() function.

### <b>How to use it ?</b>

In order to make the program work, you must do the following :

 - Set the boot mode in development mode (BOOT1 switch position is 2-3, BOOT0 switch position doesn't matter).
 - Open your preferred toolchain
 - Rebuild all files and load your image into target memory. Code can be executed in this mode for debugging purposes.

 Next, this program can be run in boot from flash mode. This is done by following the instructions below:

 - Resort to CubeProgrammer to add a header to the generated binary Project.bin with the following command
   - *STM32_SigningTool_CLI.exe -bin Project.bin -nk -of 0x80000000 -t fsbl -o Project-trusted.bin -hv 2.3 -dump Project-trusted.bin*
   - The resulting binary is Project-trusted.bin.
 - Next, in resorting again to CubeProgrammer, load the binary and its header (Project-trusted.bin) in the board external Flash at address 0x7000'0000.
 - Set the boot mode in boot from external Flash (BOOT0 switch position is 1-2 and BOOT1 switch position is 1-2).
 - Press the reset button. The code then executes in boot from external Flash mode.






**Warning** If using CubeProgrammer v2.21 version or more recent, add *-align* option in the command line.
