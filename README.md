# Cisco Switch Serial Configuration Script

This script configures supported Cisco IOS switches through a serial console connection.

It is designed to be device-agnostic and can work with systems that provide access to a serial console device.

It supports switches using either:

- `FastEthernet1/0/x`
- `GigabitEthernet1/0/x`

The script checks ports `1/0/3` through `1/0/24` for:

```text
speed auto
spanning-tree portfast
```

If the settings are already correct, no changes are made.

If settings are missing, only the missing settings are applied. Existing VLANs and unrelated interface configuration are preserved.

---

# Requirements

## Hardware

You need:

- A supported Cisco IOS switch
- A console cable or USB-to-serial adapter
- Physical access to the switch
- A computer or device with access to the serial adapter
- Access to the switch's MODE button if password recovery is required

The connected switch should expose a serial console that can be accessed by your device.

Typical Cisco console settings are:

```text
Baud rate: 9600
Data bits: 8
Parity: None
Stop bits: 1
Flow control: None
```

---

## Software

Your device needs:

- Python 3
- Python virtual environment support
- `pip`
- `pyserial`

Check Python:

```bash
python3 --version
```

You should have Python 3 installed before continuing.

---

# 1. Connect the Switch

Connect your device to the switch using the console cable or USB-to-serial adapter.

Make sure the switch is powered on.

Find the serial device exposed by your operating system.

Examples may include:

```text
/dev/cu.usbserial-1130
/dev/ttyUSB0
/dev/ttyACM0
COM3
COM4
```

The exact device name depends on your operating system and serial adapter.

Make sure no other program is currently using the serial port.

Programs that may already have the device open include:

```text
screen
minicom
picocom
PuTTY
another Python script
```

Close any existing serial console session before running the script.

---

# 2. Place the Script in a Directory

Create or enter a directory for the script.

For example:

```bash
mkdir -p ~/switch-config
cd ~/switch-config
```

Place the script in this directory as:

```text
configure_switch_serial.py
```

---

# 3. Create a Python Virtual Environment

Create the virtual environment:

```bash
python3 -m venv .venv
```

Activate it.

On systems using a POSIX-style shell:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

Once activated, your prompt will usually show something similar to:

```text
(.venv)
```

---

# 4. Install pyserial

Install the required Python package:

```bash
python3 -m pip install pyserial
```

Verify that it installed successfully:

```bash
python3 -c "import serial; print(serial.__version__)"
```

---

# 5. Configure the Serial Device

The script needs to know which serial device to use.

Depending on the version of the script, it may:

- automatically detect the serial adapter
- ask you to select a serial device
- use a configured serial device path

Example serial device values:

```text
/dev/ttyUSB0
/dev/ttyACM0
/dev/cu.usbserial-1130
COM3
```

Do not assume the same serial device name will be used on every computer.

---

# 6. Run the Script

Run:

```bash
python3 configure_switch_serial.py
```

The script will:

1. Open the serial console.
2. Wait for the switch to finish POST and boot IOS.
3. Handle messages such as:

```text
Press RETURN to get started!
```

4. Wait for a real IOS prompt before attempting authentication.
5. Attempt to enter privileged EXEC mode.
6. Detect whether the switch uses FastEthernet or GigabitEthernet access ports.
7. Check ports `1/0/3` through `1/0/24`.
8. Verify:

```text
speed auto
spanning-tree portfast
```

9. Apply only missing settings.
10. Save the configuration if changes were made.
11. Verify the configuration again.

---

# Interface Detection

The script supports both FastEthernet and GigabitEthernet switches.

A GigabitEthernet switch may contain interfaces such as:

```text
Gi1/0/1
Gi1/0/2
Gi1/0/3
...
Gi1/0/24
```

The script will use:

```text
GigabitEthernet1/0/3
...
GigabitEthernet1/0/24
```

A FastEthernet switch may contain:

```text
Fa1/0/1
Fa1/0/2
Fa1/0/3
...
Fa1/0/24
```

The script will use:

```text
FastEthernet1/0/3
...
FastEthernet1/0/24
```

Some switches contain FastEthernet access ports and separate GigabitEthernet uplinks.

The script should choose the interface family containing the most ports in the target `3-24` range instead of simply choosing the first GigabitEthernet interface it sees.

---

# Already Configured Switch

If all required settings are already correct, the script should report something similar to:

```text
===== CURRENT CONFIGURATION =====

GigabitEthernet1/0/3       PASS
GigabitEthernet1/0/4       PASS
GigabitEthernet1/0/5       PASS
...
GigabitEthernet1/0/24      PASS

Everything is already configured correctly.
No changes made.
```

On a FastEthernet switch, the same output will use:

```text
FastEthernet1/0/x
```

---

# Partially Configured Switch

If a port is missing a required setting, the script reports it.

Example:

```text
FastEthernet1/0/7          FAIL  missing: speed auto
FastEthernet1/0/8          PASS
```

The script only applies the missing setting.

For example:

```text
interface FastEthernet1/0/7
 speed auto
```

Existing settings such as:

```text
switchport access vlan 803
description Example
shutdown
```

are left unchanged unless the script explicitly manages them.

---

# Configuration Requirements

For every existing target port from `1/0/3` through `1/0/24`, the script verifies:

```text
speed auto
spanning-tree portfast
```

The script does not require ports `1/0/1` or `1/0/2` to use these settings.

---

# Saving the Configuration

If the script makes changes, it saves them using:

```text
copy running-config startup-config
```

If the switch is already configured correctly, no save operation is required.

---

# Boot Handling

The script must wait for the switch to completely boot before testing authentication.

Normal boot output may include:

```text
POST: PortASIC Memory Tests : Begin
POST: PortASIC Memory Tests : End, Status Passed
Waiting for Stack Master Election...
Cisco IOS Software...
Press RETURN to get started!
```

This does not indicate an authentication failure.

The script should continue waiting until IOS reaches a usable prompt such as:

```text
Switch>
```

or:

```text
Switch#
```

Only after reaching a valid IOS prompt should the script attempt authentication.

---

# Password Handling

The script uses the configured known password when attempting to access privileged EXEC mode.

It may encounter:

```text
Switch>
```

and then issue:

```text
enable
```

If prompted:

```text
Password:
```

the script submits the configured password.

If the password succeeds, the script continues normally.

---

# Password Recovery

Password recovery should only start when:

1. IOS has completely booted.
2. A valid IOS prompt has been reached.
3. The known password has actually been rejected.

The script should not begin password recovery while the switch is still performing POST or loading IOS.

If password recovery is required and the switch supports the Cisco `switch:` boot-loader recovery process:

1. Power-cycle the switch.
2. Hold the physical MODE button.
3. Continue holding it until:

```text
switch:
```

appears.
4. Release the MODE button.
5. Allow the script to continue.

The recovery process should preserve the existing switch configuration whenever possible.

The script should temporarily prevent the old configuration from loading, boot IOS, regain privileged access, restore the configuration, replace the unknown enable password, and save the configuration again.

---

# Running the Script Again

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Then run:

```bash
python3 configure_switch_serial.py
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python configure_switch_serial.py
```

---

# Exit the Virtual Environment

When finished:

```bash
deactivate
```

---

# Troubleshooting

## Serial Device Not Found

Find which serial device your operating system assigned to the adapter.

Examples include:

```text
/dev/ttyUSB0
/dev/ttyACM0
/dev/cu.usbserial-1130
COM3
```

Update or select the appropriate serial device before running the script.

---

## Serial Device Is Busy

Only one application should normally access the serial console at a time.

Close applications such as:

```text
screen
minicom
picocom
PuTTY
```

and stop any other instance of the Python script.

Then run the script again.

---

## Script Appears to Be Waiting During Boot

This is normal.

Cisco switches may take several minutes to complete:

```text
POST
flash initialization
stack election
IOS loading
interface initialization
```

Wait for the script to detect:

```text
Press RETURN to get started!
```

or an IOS prompt.

Do not assume that long POST output means the script has failed.

---

## Wrong Interface Type Detected

The script should automatically distinguish between:

```text
FastEthernet
```

and:

```text
GigabitEthernet
```

based on the interfaces reported by:

```text
show interfaces status
```

For switches containing both interface types, the script should choose the family containing the target access ports from `1/0/3` through `1/0/24`.
