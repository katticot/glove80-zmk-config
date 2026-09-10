---
title: "MoErgo Glove80: Personal Guide & Architecture Reference"
aliases:
  - Glove 80
  - my keyboard
  - Glove80 Firmware Guide
  - Glove 80 ZMK
tags:
  - keyboard
  - hardware
  - zmk
  - zephyr
  - embedded
  - reverse-engineering
  - nrf52840
type: wiki
status: active
created: 2026-05-16
updated: 2026-09-09
summary: "Comprehensive personal configuration guide and deep technical architecture reference for the MoErgo Glove80 split ergonomic keyboard, covering daily setup, Sunaku layout, custom ZMK firmware, flash memory map, reverse engineering, and hardware recovery failsafes."
---

# MoErgo Glove80: Personal Guide & Architecture Reference

The **MoErgo Glove80** is a contoured split ergonomic mechanical keyboard designed for maximum typing comfort and efficiency. This document combines personal configuration notes and daily driver workflows with a technical reference covering the underlying firmware architecture, flash memory layout, reverse-engineering procedures, and hardware recovery methods.

---

## 1. Personal Setup & Daily Driver Notes

### Ergonomic Transition
* **Device:** MoErgo Glove80 (White, low-profile Kailh Choc v1 switches).
* **Ergonomics:** Pronounced 3D contoured key wells and integrated palm rests significantly reduce ulnar deviation, pronation, and finger extension strain compared to flat keyboards (see [[Keyboard]]).
* **Learning Curve:** Transitioning to the contoured 3D wells requires building muscle memory for vertical column alignment and thumb cluster chords.
* **Official User Guide:** [Glove80 User Guide (MoErgo PDF)](https://www.moergo.com/files/glove80-user-guide.pdf#h.mvmyh03asyki)
* **Visual Layer Simulator:** Visual 3D contour and layer reference is available in the local companion tool `[[glove80_glorious_engrammer.html]]`.

### Sunaku Layout
The daily driver layout is based on **Sunaku's Glove80 Layout**, featuring Colemak-DH / Engrammer alphas, bilateral home row modifiers, dedicated thumb layer switching, and modal navigation.

![[sunaku-glove80-keyboard-layers.pdf]]

---

## 2. Keymap Configuration & Build Workflow

### Firmware Ecosystem: MoErgo Fork vs. Upstream ZMK
MoErgo maintains a specialized fork of [ZMK Firmware](https://zmk.dev) (`moergo-sc/zmk`) to support Glove80-specific hardware features:
* Dynamic per-key RGB matrix & underglow status indicators (`zmk,underglow-indicators`).
* Power management and low-quiescent battery telemetry (`zmk,battery-nrf-vddh`).
* Unified UF2 packaging with dual-family bootloader tagging.

Because of these custom drivers, standard upstream ZMK builds cannot be flashed directly without MoErgo board definitions and DTS overlays.

### Configuration Methods

1. **Web Layout Editor:**
   * Graphical visual editor: [my.glove80.com Layout Profile](https://my.glove80.com/#/layout/user/57d36cd9-5b7e-4daa-93b2-77bf1560edb1)
   * Generates compiled `.uf2` binaries directly in the browser via cloud build workers.

2. **Personal Git Repository & CI/CD Pipeline:**
   * Custom repository: [katticot/glove80-zmk-config](https://github.com/katticot/glove80-zmk-config) (forked from [moergo-sc/glove80-zmk-config](https://github.com/moergo-sc/glove80-zmk-config)).
   * Edit keymaps, hold-tap behaviors, combos, and macros in `config/glove80.keymap`.
   * Pushing commits to `main` triggers a **GitHub Actions** workflow that automatically compiles and outputs the unified `glove80.uf2` firmware artifact.

---

## 3. Hardware & System Overview

| Component | Specification |
|---|---|
| **MCU / SoC** | 2× Nordic Semiconductor **nRF52840** (32-bit ARM Cortex-M4F @ 64 MHz, FPU, 1 MB Flash, 256 KB RAM) |
| **Wireless Module** | 2× **Raytac MDBT50Q-1MV2** with integrated high-gain ceramic/PCB antenna |
| **Switch Matrix** | 80 keys total (40 per half: 6 rows × 6 columns well + 6-key curved thumb cluster per side) |
| **Key Switches** | Low-profile Kailh Choc v1 mechanical switches (hot-swap or soldered variants) |
| **RGB Lighting** | 80 addressable WS2812 LEDs (40 per half) driven via SPI @ 4 MHz |
| **Power Supply** | Independent ~500 mAh LiPo batteries with onboard linear charging ICs |
| **Firmware Stack** | [ZMK Firmware](https://zmk.dev) (fork `moergo-sc/zmk`) on [Zephyr RTOS](https://zephyrproject.org) |

```
+-------------------------------------------------------------------------+
|                        MoErgo Glove80 Firmware                          |
+-------------------------------------------------------------------------+
| Keymap Engine & Behaviors | RGB Matrix Subsystem | Battery & Power Mgmt |
+-------------------------------------------------------------------------+
|                  ZMK Firmware Core (moergo-sc/zmk Fork)                 |
|  - Split BLE central/peripheral logic   - Bluetooth profile management  |
|  - Matrix transformation (glove80.dtsi) - Behavior macro / Hold-Tap     |
+-------------------------------------------------------------------------+
|                             Zephyr RTOS                                 |
|  - Preemptive multithreading kernel     - Device Driver Model           |
|  - Devicetree (DTS) hardware mapping    - Low-power tickless idle       |
|  - Nordic nRF5x HAL / SoftDevice BLE    - SAADC / I2C / SPI / GPIO      |
+-------------------------------------------------------------------------+
|                   Raytac MDBT50Q-1MV2 (nRF52840 MCU)                    |
+-------------------------------------------------------------------------+
```

---

## 4. Split Topology & Controller Roles

* **Left Half (Central / Master):**
  * Configured with `CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y`.
  * Manages wired USB 2.0 Full-Speed (12 Mbps) HID communication with the host PC.
  * Handles up to 4 BLE host profiles and evaluates active layers.
  * Processes hold-tap behaviors, chording, combos, and macros.
  * Acts as RGB master for underglow and layer animation synchronization.
  * *Must be connected via USB-C when typing over a wired connection.*
* **Right Half (Peripheral / Slave):**
  * Scans local switch matrix and monitors local battery state.
  * Streams debounced keypress/release events wirelessly over BLE split notifications to the Left half.
  * The Right USB-C port is strictly for battery charging and bootloader flashing; keystrokes are never routed over USB directly from the right half to the host.

---

## 5. Flash Memory Map (1 MB Flash per Half)

```
0x0000_0000 +-----------------------------------------------+
            | MBR (Master Boot Record)                     |  4 KB
0x0000_1000 +-----------------------------------------------+
            | Nordic S140 SoftDevice (BLE Stack)            |  148 KB - 152 KB
0x0002_6000 +-----------------------------------------------+
            | Application Firmware (code_partition)         |  792 KB
            | - Vector Table (SP, Reset Handler)            |
            | - Zephyr RTOS Kernel + Device Drivers         |
            | - ZMK Keyboard Matrix Engine                 |
            | - Compiled Keymaps, Behaviors, Macros (.rodata)|
0x000E_C000 +-----------------------------------------------+
            | Storage Partition (storage_partition / NVS)   |  32 KB
            | (BLE pairing keys, dynamic profiles, runtime) |
0x000F_4000 +-----------------------------------------------+
            | Adafruit nRF52 Dual-Bank UF2 Bootloader       |  48 KB
0x0010_0000 +-----------------------------------------------+
```

* **Application Base Address:** `0x00026000` (SoftDevice S140 v6.x) or `0x00027000` (SoftDevice S140 v7.x).
* **RAM Layout:** `0x20000000` to `0x20040000` (256 KB RWX).

---

## 6. Hardware Pinouts & Devicetree Bindings

### A. Switch Matrix (6 Rows × 7 Columns per half = 14 Total Columns)
* **Scanning Mode:** `col2row` (`compatible = "zmk,kscan-gpio-matrix"`).
* **Debounce:** 4 ms press, 20 ms release (`debounce-press-ms = <4>`, `debounce-release-ms = <20>`).

| Half | Row GPIOs | Column GPIOs |
|---|---|---|
| **Left Half** (`glove80_lh.dts`) | `P0.26`, `P0.05`, `P0.06`, `P0.08`, `P0.07`, `P1.09` | `P1.08`, `P1.04`, `P1.06`, `P1.07`, `P1.05`, `P1.03`, `P1.01` (Thumb) |
| **Right Half** (`glove80_rh.dts`) | `P0.26`, `P0.05`, `P0.07`, `P1.08`, `P0.11`, `P0.12` | `P1.06` (Thumb), `P1.04`, `P0.02`, `P1.07`, `P1.05`, `P1.03`, `P1.01` |

### B. RGB LEDs & Status Indicators
* **Per-Key RGB LEDs:** 40 WS2812 addressable LEDs per half driven over SPI MOSI (`worldsemi,ws2812-spi` @ 4 MHz).
  * **Left MOSI Data:** `P0.27` | Power Gate (`WS2812_CE`): `P0.31`
  * **Right MOSI Data:** `P0.13` | Power Gate (`WS2812_CE`): `P0.19`
* **MoErgo Underglow Status Overlay (`zmk,underglow-indicators`):**
  * Layer state indicators: LEDs `35, 29, 23, 17, 11, 6`
  * Left & Right Battery indicators: LEDs `36, 30, 24, 18, 12, 7` and `37, 31, 25, 19, 13, 8`
  * Lock keys: CapsLock (`22`), NumLock (`16`), ScrollLock (`10`)
* **Rear Status LED:** Driven via PWM (`&pwm0`). Left: `P1.15`, Right: `P0.16`.

### C. Battery ADC Telemetry
* **Driver:** `zmk,battery-nrf-vddh` (measures battery voltage directly via internal VDDH regulator ADC channel; no external resistor divider needed).
* **Proxy:** Peripheral battery level transmitted over BLE GATT to central for host reporting (`CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y`).

### D. 6-Pin Expansion Header (`moergo,glove80-ext`)
| Pin Name | Left Hand Pin | Right Hand Pin | Function |
|---|---|---|---|
| **EXT1** | `P0.22` | `P0.21` | GPIO / UART0 TX |
| **EXT2** | `P0.21` | `P0.24` | GPIO / UART0 RX |
| **EXT3** | `P0.24` | `P0.20` | GPIO / I2C / SPI |
| **EXT4** | `P0.20` | `P0.25` | GPIO / I2C / SPI |
| **EXT5** | `P0.25` | `P0.22` | GPIO |
| **EXT6** | `P1.00` | `P1.00` | GPIO / SWO |

---

## 7. UF2 Container Format & Unified Flashing

### UF2 Block Structure (512 Bytes)
Each 512-byte block contains a 32-byte header, 256 bytes of payload data, 220 bytes of padding, and a 4-byte footer:
* `magicStart0`: `0x0A324655` (`"UF2\n"`)
* `magicStart1`: `0x9E5D5157`
* `flags`: `0x00002000` (indicates Family ID is present)
* `targetAddr`: 32-bit flash destination address
* `payloadSize`: 256 bytes (`0x00000100`)
* `magicEnd`: `0x0AB16F30`

### Unified UF2 Dual-Family ID Mechanism
Glove80 firmware builds merge both halves into a single `.uf2` file using distinct Family IDs:
* **LH Family ID:** `0x9807B007`
* **RH Family ID:** `0x9808B007`
* When dragged onto `GLV80LHBOOT` or `GLV80RHBOOT`, each bootloader automatically flashes its matching blocks and ignores the other side.

---

## 8. Reverse Engineering & Binary Extraction

### A. Python Script to Unpack `.uf2` to Raw Binary (`unpack_uf2.py`)
```python
import struct, sys

def unpack_uf2(uf2_file, bin_file):
    UF2_MAGIC_START0 = 0x0A324655
    UF2_MAGIC_START1 = 0x9E5D5157
    UF2_MAGIC_END    = 0x0AB16F30
    chunks = {}

    with open(uf2_file, "rb") as f:
        while block := f.read(512):
            if len(block) < 512: break
            m0, m1, flags, addr, sz, blk_no, num_blks, family = struct.unpack("<8I", block[:32])
            mend = struct.unpack("<I", block[508:512])[0]
            if m0 != UF2_MAGIC_START0 or m1 != UF2_MAGIC_START1 or mend != UF2_MAGIC_END:
                continue
            chunks[addr] = block[32:32+sz]

    min_addr, max_addr = min(chunks.keys()), max(chunks.keys()) + 256
    print(f"[+] Flash Range: 0x{min_addr:08X} - 0x{max_addr:08X} ({max_addr - min_addr} bytes)")

    assembled = bytearray(b"\xFF" * (max_addr - min_addr))
    for addr, payload in chunks.items():
        assembled[addr - min_addr : addr - min_addr + len(payload)] = payload

    with open(bin_file, "wb") as f_out:
        f_out.write(assembled)
    print(f"[+] Extracted raw binary to: {bin_file}")

if __name__ == "__main__":
    unpack_uf2(sys.argv[1], sys.argv[2])
```

### B. Disassembly in Ghidra / IDA Pro
1. Import the unpacked `.bin` file.
2. **Processor:** `ARM Cortex` 32-bit Little-Endian (ARMv7E-M / Cortex-M4F).
3. **Base Address:** `0x00026000` (or `0x00027000`).
4. **RAM Region:** `0x20000000` to `0x20040000` (256 KB, RWX).
5. Disassemble in **Thumb Mode** (`TMode = 1`). Vector table at `0x00026000` (Initial SP) and `0x00026004` (Reset Handler).

### C. Recovering Keymaps from `.rodata`
In ZMK, key behaviors are compiled into contiguous arrays of 12-byte structs:
```c
struct zmk_behavior_binding {
    const char *behavior_dev; // Pointer to string ("kp", "mo", "lt", "mt", "bt", etc.)
    uint32_t param1;           // HID Keycode or Layer Index
    uint32_t param2;           // Modifier or Secondary Parameter
};
```
* Each 80-key layer occupies $80 \times 12 = 960$ bytes in `.rodata`.
* Scanning for pointers to `"kp"` followed by valid USB HID keycodes (`0x04` = 'A', `0x2C` = Space) allows full reconstruction of all configured layers and macros.
* **Glorious Engrammer v38 Binary Audit Findings (`0x0006362C` - `0x00069000`):**
  * Contains **24 compiled ZMK layers** ($24 \times 960 = 23,040$ bytes of `.rodata`).
  * **Base Layer (L0):** Colemak-DH Engrammer (`Q W F P B` / `A R S T G` / `J L U Y` / `M N E I O`).
  * **Bilateral HRMs:** Inner-to-Outer: Shift $\rightarrow$ Ctrl $\rightarrow$ Gui $\rightarrow$ Alt (`T/S/R/A` on LH, `N/E/I/O` on RH).
  * **Thumb Triggers:** LH Lower Outer is `Space` (`0x7002C`, activates L12 Nav/Num hold); RH Lower Outer is `Delete` (`0x7004C`, deletes character on macOS).

---

## 9. Complete 24-Layer ZMK Firmware Architecture

Disassembly of `Glorious Engrammer v38.uf2` (`0x0006362C` - `0x00069000`) reveals 24 distinct compiled layers ($24 \times 960 = 23,040$ bytes in `.rodata`):

| Layer | Flash Offset | Layer Name | Core Purpose & Behavior |
|---|---|---|---|
| **L00** | `0x6362C` | **Base Layer (Colemak-DH Engrammer)** | Alphas (`W F P B` / `A R S T G` / `J L U Y` / `M N E I O`), bilateral HRMs, thumb layer access. |
| **L01** | `0x639EC` | **Quick Access & Layer Hold** | Intermediate layer hold evaluation and transient modifier pass-through. |
| **L02–L06** | `0x63DAC` | **Left Bilateral HRM Resolvers** | Dedicated mod-tap state resolvers for Left Pinky (`A`), Ring (`R`), Mid (`S`), Index (`T`), Inner (`G`). |
| **L07–L11** | `0x6506C` | **Right Bilateral HRM Resolvers** | Dedicated mod-tap state resolvers for Right Inner (`M`), Index (`N`), Mid (`E`), Ring (`I`), Pinky (`O`). |
| **L12** | `0x6632C` | **Tmux & Window Management** | Tmux pane navigation (`mod_tab_switcher`), session switching, line/word extensions (`extend_line`). |
| **L13** | `0x666EC` | **Text Selection & Line Extend** | Direct text block selection (`select_line`, `select_word`), sticky shift modifiers. |
| **L14** | `0x66AAC` | **Code Refactor & Word Select** | Code block refactoring, cursor jump expansions, structured word manipulation. |
| **L15** | `0x66E6C` | **Weather & Common Emojis** | Direct Unicode macro injection (`emoji_cloudy`, `emoji_mostly_sunny`, `emoji_moon_gibbous`). |
| **L16** | `0x6722C` | **Symbol & Question Emojis** | Extended emoji symbols, punctuation icons, and question glyphs. |
| **L17** | `0x675EC` | **Directional Numpad & Symbols** | Right-hand 3×3 numeric keypad, math operators (`+ - * / =`), and cursor arrows. |
| **L18** | `0x679AC` | **Underglow & Linux Magic SysRq** | WS2812 RGB lighting controls, brightness stepping, Linux kernel emergency SysRq triggers. |
| **L19** | `0x67D6C` | **World Diacritics (272 Macros)** | Direct access to international accents (acute, grave, circumflex, umlaut, tilde, ring) & currencies (€, £, ¥, ₩, ¢). |
| **L20** | `0x6812C` | **Transparent Pass-Through** | Base passthrough layer for momentary overrides. |
| **L21** | `0x684EC` | **Fallback QWERTY Layer** | Full standard QWERTY alpha mapping for gaming or unconfigured guest typing. |
| **L22** | `0x688AC` | **Function Hub & Switcher** | Extended function keys (`F11`–`F24`), volume/media playback, direct layer toggle bank. |
| **L23** | `0x68C6C` | **Hardware Magic & Bluetooth** | BLE profile selection (1–4), USB/BLE output toggle, BLE clear bonds, DFU bootloader triggers. |

---

## 9.1 Streamlined Minimal Architecture (Recommended Daily Driver)

To eliminate bloat, accidental macro triggers, and complex dead-key chords, the layout is streamlined down to the essential functional layers:

| Clean Layer | Name | Trigger Binding | Core Functionality |
|---|---|---|---|
| **L00 (Base)** | **Colemak-DH Engrammer** | Default active layer | Full alpha typing (`W F P B` / `A R S T G` / `J L U Y` / `M N E I O`), bilateral HRMs (`Alt/Gui/Ctrl/Shift`). |
| **L01 (Numpad/Nav)** | **Directional Numpad & Symbols** | Hold `Tab` (LH T2) or `Enter` (LH T6) | Right-hand 3×3 numpad (`7 8 9`, `4 5 6`, `1 2 3`, `0`), math operators (`+ - * / =`), and cursor arrows. |
| **L02 (Magic)** | **Hardware Magic & Bluetooth** | Tap `Magic` (LH C6R6) | Bluetooth profile switching (1–4), USB toggle, battery telemetry, and bootloader mass-storage trigger. |
| **L03–L12 (HRM)** | **Bilateral HRM Resolvers** | Automatic on home-row hold | 10-state machine resolving mod-tap rolls vs chords on opposite hands. |

* **Clean Keymap File:** Generated and stored in `Downloads/glove80_cleaned_minimal.keymap`.
* **Pruned Layers:** Dropped L14 (Code refactor), L15 (Weather emojis), L16 (Symbol emojis), L18 (Magic SysRq), L19 (272 World diacritic macros), and L21 (QWERTY fallback).

---

## 10. Bilateral Home Row Modifier (HRM) State Machine

The Glove80 Glorious Engrammer layout eliminates accidental modifier misfires via a **10-state Bilateral HRM State Machine** (Layers 2–11):
* When a Left Hand home row key (`A`, `R`, `S`, `T`) is held, the Right Hand switches into a mirrored resolution layer.
* If a Right Hand key is struck while the Left modifier is held, the modifier triggers immediately as a clean chord (`⌘ Cmd + Key` / `⌥ Alt + Key`).
* If another key on the *same* hand is pressed rapidly (same-hand rolling), the key resolves strictly as a rapid alpha tap rather than a stuck modifier.

---

## 11. Bootloader, Flashing & Recovery Guide

### A. Entering Bootloader Mode on Power-Up (Hardware Failsafe)
* **Left Half:** Power switch OFF $\rightarrow$ Connect USB-C $\rightarrow$ Hold **`Magic + E`** (`C6R6 + C3R3`) $\rightarrow$ Switch ON $\rightarrow$ Mounts as **`GLV80LHBOOT`**.
* **Right Half:** Power switch OFF $\rightarrow$ Connect USB-C $\rightarrow$ Hold **`I + PgDn`** (`C6R6 + C3R3`) $\rightarrow$ Switch ON $\rightarrow$ Mounts as **`GLV80RHBOOT`**.
* **LED Status:** Slow pulsing red LED indicates the bootloader is ready for flashing. Drag and drop the `.uf2` file onto the mounted drive.

### B. Factory Reset (Clear Non-Volatile Storage / BLE Bonds)
1. Turn OFF both halves.
2. Hold **`C6R6 + C3R2`** (**`Magic + 3`** on LH / **`PgDn + 8`** on RH).
3. Switch power ON, hold for 5 seconds, switch OFF. Repeat on the other half.
4. Turn both halves ON at the exact same moment.
5. Toggle RGB ON (**`Magic + T`**) to verify sync, toggle OFF, and wait 60 seconds for split bonding keys to write to flash.

---

## 12. References & Official Links

* **Official User Documentation:** [docs.moergo.com](https://docs.moergo.com)
* **MoErgo User Guide PDF:** [glove80-user-guide.pdf](https://www.moergo.com/files/glove80-user-guide.pdf#h.mvmyh03asyki)
* **Web Layout Editor:** [my.glove80.com](https://my.glove80.com)
* **Personal Keymap Repo:** [github.com/katticot/glove80-zmk-config](https://github.com/katticot/glove80-zmk-config)
* **MoErgo ZMK Fork Repository:** [github.com/moergo-sc/zmk](https://github.com/moergo-sc/zmk)
* **Glove80 ZMK Config Repository:** [github.com/moergo-sc/glove80-zmk-config](https://github.com/moergo-sc/glove80-zmk-config)
* **Related Vault Notes:** [[Keyboard]], [[glove80_glorious_engrammer.html]]

