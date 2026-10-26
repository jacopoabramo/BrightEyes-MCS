# BrightEyes-MCSLL

> Applicability: the register and FIFO tables use firmware v1 snake-case names.
> Saved HDF5 files retain legacy names through
> [legacy_names.py](../src/brighteyes_mcs/storage/legacy_names.py); see the
> [HDF5 compatibility reference](h5_mcs_scheme_v0_0_1.md).
> The historical board/pinout material does not identify an exact bitfile revision.
> Confirm pin assignments and registers against the selected bitfile before using
> it with an instrument; this document is not verification of connected hardware.

The BrightEyes Microscope Control Software Low-Level is a collections of firmwares for NI FPGA in order to be used with BrightEyes-MCS.
Documentation and usage you can find in [BrightEyes-MCS repository](https://github.com/VicidominiLab/BrightEyes-MCS).

**Copyright** (C) 2023 Istituto Italiano di Tecnologia

**Author:** Mattia Donato

**Credits to:** Marco Castello, Giorgio Tortarolo, Simonluca Piazza, Eli Slenders

**Closed-Source Firmware License Agreement:** This license grants you a non-exclusive, non-transferable permission to download and utilize our proprietary firmware free of charge. However, you are required to use this firmware exclusively in conjunction with open-source software, such as [BrightEyes-MCS](https://github.com/VicidominiLab/BrightEyes-MCS). Modifying, distributing, or employing it with closed-source software is strictly prohibited. We actively endorse and support the use of this firmware in educational institutions, including schools, universities, as well as in both public and private research organizations. All rights to the firmware are retained by us. The firmware is provided "as is" with absolutely no warranty. We disclaim all liability for any damages. This license may be terminated at your discretion or by us. Your use of the firmware signifies your agreement to this Agreement.

If you have bugs to report or you have requests for adding or modifying firmware functionalities, please feel free to contact us. We are open to collaborations!





# BrightEyes-MCS-LowLevel Firmwares

## I/O Table
|                                           | I/O    | USB-7856R<br>(Single-Board) | USB-7856R-OEM<br>(Single-Board) | PXIe-7856R<br>(Single-Board) | PCIe-7820R<br>(Single-Board) | PXIe-7856R<br>(Double-Board)<br>(Analog side) | PXIe-7822R<br>(Double-Board)<br>(Digital side) |
|-------------------------------------------|--------|-----------------------------|---------------------------------|------------------------------|:----------------------------:|:---------------------------------------------:|:----------------------------------------------:|
| SPAD CHANNEL 0                            | IN     | Connector0/DIO0             | Connector2/DIO0                 | Connector1/DIO0              | Connector1/DIO0              |                                               | Connector1/DIO0                                |
| ...                                       | ...    | ..                          | ..                              | ...                          | ...                          | ...                                           | ...                                            |
| SPAD CHANNEL 15                           | IN     | Connector0/DIO15            | Connector2/DIO15                | Connector1/DIO15             | Connector1/DIO15             |                                               | Connector1/DIO15                               |
| SPAD CHANNEL 16                           | IN     | Connector0/DIO16            | Connector3/DIO0                 | Connector1/DIO16             | Connector1/DIO16             |                                               | Connector1/DIO16                               |
| ...                                       | ...    | ...                         | ...                             | ...                          | ...                          | ...                                           | ...                                            |
| SPAD CHANNEL 24                           | IN     | Connector0/DIO24            | Connector3/DIO8                 | Connector1/DIO24             | Connector1/DIO24             |                                               | Connector1/DIO24                               |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| SPAD ENABLE                               | OUT    | Connector0/DIO25            | Connector1/DIO12                | Connector1/DIO25             | Connector1/DIO25             |                                               | Connector1/DIO25                               |
| SPAD SCLK                                 | OUT    | Connector0/DIO26            | Connector1/DIO15                | Connector1/DIO26             | Connector2/DIO25             |                                               | Connector2/DIO25                               |
| SPAD SDATA                                | OUT    | Connector0/DIO27            | Connector1/DIO14                | Connector1/DIO27             | Connector2/DIO24             |                                               | Connector2/DIO24                               |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| Laser 0                                   | OUT    | Connector0/DIO28            | Connector1/DIO0                 | Connector1/DIO28             | Connector1/DIO28             |                                               | Connector1/DIO28                               |
| Laser 1                                   | OUT    | Connector0/DIO29            | Connector1/DIO1                 | Connector1/DIO29             | Connector1/DIO29             |                                               | Connector1/DIO29                               |
| Laser 2                                   | OUT    | Connector0/DIO30            | Connector1/DIO2                 | Connector1/DIO30             | Connector1/DIO30             |                                               | Connector1/DIO30                               |
| Laser 3                                   | OUT    | Connector0/DIO31            | Connector1/DIO3                 | Connector1/DIO31             | Connector1/DIO31             |                                               | Connector1/DIO31                               |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| AnalogINx                                 | IN     | Connector1/AIx              | Connector0/AIx                  | Connector0/AIx               |                              | Connector0/AIx                                |                                                |
| AnalogOUTx                                | OUT     | Connector1/AOx              | Connector0/AOx                  | Connector0/AOx               |                              | Connector0/AOx                                |                                                |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| Pixel sync.                               | OUT    | Connector1/DIO5             | Connector1/DIO5                 | Connector0/DIO5              | Connector2/DIO29             |                                               | Connector2/DIO29                               |
| Line sync.                                | OUT    | Connector1/DIO6             | Connector1/DIO6                 | Connector0/DIO6              | Connector2/DIO30             |                                               | Connector2/DIO30                               |
| Frame sync.                               | OUT    | Connector1/DIO7             | Connector1/DIO7                 | Connector0/DIO7              | Connector2/DIO31             |                                               | Connector2/DIO31                               |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| Debug OUT (Analog Output updated trigger) | OUT    | Connector1/DIO8             | Connector1/DI13                 | Connector0/DIO8              |                              | Connector0/DIO9                               |                                                |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| Det_extra_0                               | IN     | Connector1/DIO0             | Connector3/DI9                  | Connector0/DIO0              | Connector1/DIO26             |                                               | Connector1/DIO26                               |
| Det_extra_1                               | IN     | Connector1/DIO1             | Connector3/DI10                 | Connector0/DIO1              | Connector1/DIO27             |                                               | Connector1/DIO27                               |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| Laser Debug                               | OUT    | Connector1/DIO11            | Connector1/DIO9                 | Connector0/DIO11             |                              |                                               |                                                |
| Laser 0 (Duplicated)                      | OUT    | Connector1/DIO12            |                                 | Connector0/DIO12             |                              |                                               |                                                |
| Laser 1 (Duplicated)                      | OUT    | Connector1/DIO13            |                                 | Connector0/DIO13             |                              |                                               |                                                |
| Laser 2 (Duplicated)                      | OUT    | Connector1/DIO14            |                                 | Connector0/DIO14             |                              |                                               |                                                |
| Laser 3 (Duplicated)                      | OUT    | Connector1/DIO15            |                                 | Connector0/DIO15             |                              |                                               |                                                |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| AD5764_SDATA                              | OUT    |                             |                                 |                              | Connector0/DIO26             |                                               | Connector0/DIO26                               |
| AD5764_SCLK                               | OUT    |                             |                                 |                              | Connector0/DIO27             |                                               | Connector0/DIO27                               |
| AD5764_SSYNC                              | OUT    |                             |                                 |                              | Connector0/DIO28             |                                               | Connector0/DIO28                               |
|                                           |        |                             |                                 |                              |                              |                                               |                                                |
| GI_DAC_ADC                                | IN/OUT |                             |                                 |                              | [Connector3]                 |                                               | [Connector3]                                   |


## Registers

The register table is in [the mcs service package](../src/brighteyes_mcs/services/registers.md), where the service reads the description of each register it serves.

## FIFOs:

| Type | Board      | Type | Read/Write | Tested                                             |
|------|------------|------|------------|----------------------------------------------------|
| 1    | stream_in | U64  | Write <br> \(from PC to FPGA\)      | Used only for the special case "custom positions"  |
| 2    | stream_out_main | U64  | Read <br> \(from FPGA to PC\)      | Data from SPAD acquired from Digital Channels 25+2 |
| 3    | stream_out_aux | U64  | Read <br> \(from FPGA to PC\)      | Data from selected Analog input A and B            |

### Data format:

#### Channels
Channels position on SPAD array 5x5.

|    |    |     |    |    |
|----|----|-----|----|----|
| 0  | 1  | 2   | 3  | 4  |
| 5  | 6  | 7   | 8  | 9  |
| 10 | 11  | 12  | 13  | 14  |
| 15 | 16  | 17   | 18  | 19  |
| 20 | 21  | 22   | 23  | 24  |

Moreover there are two extra channels called 25 and 26.

#### FIFO Digital
The micro-image is transmitted in a specific format made of two U64 words. 

Due to the physics of the system it has been assigned to the central elements more bits than the external ones. Here the table representing the number of bits for each channels.

Number of bit a channel:
|    |    |     |    |    |
|----|----|-----|----|----|
| 4  | 4  | 4   | 4  | 4  |
| 4  | 5  | 6   | 5  | 4  |
| 4  | 6  | 10  | 6  | 4  |
| 4  | 5  | 6   | 5  | 4  |
| 4  | 4  | 4   | 4  | 4  |

The micro-image is transmitted is trasmitted with the follwoing channels order:
- 1st word U64: 0, 1, 2, 3, 4, 5, 17, 18, 19, 20, 21, 22, 23, 24, 25. 
- 2nd word U64: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 26.




#### FIFO Analog
A word of U64 the first U32 bits are corresponding to the Analog A, and the other U32 bits are corresponding to the Analog B.
