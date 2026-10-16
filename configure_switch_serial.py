
import re
import sys
import time
import serial

# ============================================================
# SETTINGS
# ============================================================

SERIAL_PORT = "/dev/cu.usbserial-1130"
BAUD_RATE = 9600

PASSWORD = "fragfest2026"

TARGET_FIRST_PORT = 3
TARGET_LAST_PORT = 24

# If enable authentication genuinely fails after IOS has booted,
# enter the guided MODE-button recovery workflow.
RECOVER_ON_AUTH_FAILURE = True


# ============================================================
# REGEXES
# ============================================================

PRIV_PROMPT = re.compile(
    r"(?m)^[^\r\n]+#\s*$"
)

USER_PROMPT = re.compile(
    r"(?m)^[^\r\n]+>\s*$"
)

IOS_PROMPT = re.compile(
    r"(?m)^[^\r\n]+[>#]\s*$"
)

BOOTLOADER_PROMPT = re.compile(
    r"(?m)^switch:\s*$",
    re.I,
)

PASSWORD_PROMPT = re.compile(
    r"Password:\s*$",
    re.I,
)

DEST_PROMPT = re.compile(
    r"Destination filename.*\?\s*$",
    re.I,
)

CONFIRM_PROMPT = re.compile(
    r"\[confirm\]\s*$",
    re.I,
)

PRESS_RETURN = re.compile(
    r"Press RETURN to get started",
    re.I,
)

INITIAL_DIALOG = re.compile(
    r"Would you like to enter the initial configuration dialog",
    re.I,
)


# ============================================================
# SERIAL HELPERS
# ============================================================

def write_line(ser, text=""):
    ser.write((text + "\r").encode())
    ser.flush()


def read_chunk(ser):
    if not ser.in_waiting:
        return ""

    data = ser.read(
        ser.in_waiting
    ).decode(
        "utf-8",
        errors="ignore",
    )

    print(
        data,
        end="",
        flush=True,
    )

    return data


def read_for(ser, seconds):
    end = time.monotonic() + seconds
    output = ""

    while time.monotonic() < end:

        chunk = read_chunk(ser)

        if chunk:
            output += chunk
        else:
            time.sleep(0.05)

    return output


def read_until(
    ser,
    patterns,
    timeout=20,
):
    end = time.monotonic() + timeout
    output = ""

    while time.monotonic() < end:

        chunk = read_chunk(ser)

        if chunk:

            output += chunk

            if "--More--" in output:

                ser.write(b" ")
                ser.flush()

                output = output.replace(
                    "--More--",
                    "",
                )

            for pattern in patterns:

                if pattern.search(output):

                    return output, pattern

        else:

            time.sleep(0.05)

    raise TimeoutError(
        "Timed out waiting for expected output.\n\n"
        + output[-2000:]
    )


# ============================================================
# WAIT FOR IOS
# ============================================================

def wait_for_ios_ready(
    ser,
    timeout=300,
):
    """
    Wait through POST, boot, IOS startup, etc.

    This is the important fix:
    absence of a prompt does NOT mean authentication failed.
    """

    print()
    print("============================================================")
    print(" WAITING FOR SWITCH TO BE READY")
    print("============================================================")
    print()

    # Wake the console once.
    write_line(ser)

    end = time.monotonic() + timeout
    buffer = ""

    last_enter = 0

    while time.monotonic() < end:

        chunk = read_chunk(ser)

        if chunk:

            buffer += chunk

            # ------------------------------------------------
            # Bootloader prompt
            # ------------------------------------------------

            if BOOTLOADER_PROMPT.search(buffer):

                print()
                print("Boot-loader prompt detected.")

                return "bootloader"

            # ------------------------------------------------
            # Initial setup dialog
            # ------------------------------------------------

            if INITIAL_DIALOG.search(buffer):

                print()
                print(
                    ">>> Skipping initial configuration dialog"
                )

                write_line(
                    ser,
                    "no",
                )

                buffer = ""
                continue

            # ------------------------------------------------
            # Normal IOS boot finished
            # ------------------------------------------------

            if PRESS_RETURN.search(buffer):

                print()
                print(
                    ">>> IOS says Press RETURN to get started"
                )

                write_line(ser)

                buffer = ""
                last_enter = time.monotonic()

                continue

            # ------------------------------------------------
            # Privileged IOS prompt
            # ------------------------------------------------

            if PRIV_PROMPT.search(buffer):

                print()
                print(
                    ">>> IOS privileged prompt detected"
                )

                return "privileged"

            # ------------------------------------------------
            # User IOS prompt
            # ------------------------------------------------

            if USER_PROMPT.search(buffer):

                print()
                print(
                    ">>> IOS user prompt detected"
                )

                return "user"

            # Don't keep unlimited boot output in RAM.
            if len(buffer) > 20000:
                buffer = buffer[-20000:]

        else:

            # Sometimes the switch is already sitting at:
            #
            # Press RETURN to get started!
            #
            # but that text was printed before this script attached.
            #
            # Send Enter periodically while waiting.
            if (
                time.monotonic() - last_enter
                > 5
            ):

                write_line(ser)
                last_enter = time.monotonic()

            time.sleep(0.05)

    raise TimeoutError(
        "Switch did not reach an IOS prompt "
        "within 5 minutes."
    )


# ============================================================
# AUTHENTICATION
# ============================================================

def get_privileged_mode(ser):
    """
    IOS MUST already be booted before calling this.

    Returns:
        True  -> reached #
        False -> known password genuinely failed
    """

    # Get a fresh prompt.
    write_line(ser)

    output = read_for(
        ser,
        1.5,
    )

    # Already privileged.
    if PRIV_PROMPT.search(output):

        print(
            ">>> Already in privileged EXEC mode"
        )

        return True

    # Console login password.
    if PASSWORD_PROMPT.search(output):

        print(
            ">>> Console password requested"
        )

        write_line(
            ser,
            PASSWORD,
        )

        try:

            output, matched = read_until(
                ser,
                [
                    PRIV_PROMPT,
                    USER_PROMPT,
                    PASSWORD_PROMPT,
                ],
                timeout=8,
            )

        except TimeoutError:

            return False

        if matched is PRIV_PROMPT:
            return True

        if matched is PASSWORD_PROMPT:

            print(
                ">>> Known console password rejected"
            )

            return False

    # We need a > prompt before trying enable.
    if not USER_PROMPT.search(output):

        # Maybe prompt arrived a little later.
        write_line(ser)

        output += read_for(
            ser,
            2,
        )

    if PRIV_PROMPT.search(output):
        return True

    if not USER_PROMPT.search(output):

        print(
            ">>> Could not get a normal IOS prompt"
        )

        return False

    # --------------------------------------------------------
    # Try ENABLE
    # --------------------------------------------------------

    print()
    print(">>> enable")

    write_line(
        ser,
        "enable",
    )

    try:

        output, matched = read_until(
            ser,
            [
                PRIV_PROMPT,
                PASSWORD_PROMPT,
                USER_PROMPT,
            ],
            timeout=8,
        )

    except TimeoutError:

        return False

    # No password required.
    if matched is PRIV_PROMPT:

        return True

    if matched is PASSWORD_PROMPT:

        print(
            ">>> Sending known enable password"
        )

        write_line(
            ser,
            PASSWORD,
        )

        try:

            output, matched = read_until(
                ser,
                [
                    PRIV_PROMPT,
                    PASSWORD_PROMPT,
                    USER_PROMPT,
                ],
                timeout=8,
            )

        except TimeoutError:

            return False

        if matched is PRIV_PROMPT:

            print(
                ">>> Enable access successful"
            )

            return True

        print()
        print(
            ">>> Known enable password was rejected"
        )

        return False

    return False


# ============================================================
# IOS COMMANDS
# ============================================================

def ios_command(
    ser,
    command,
    timeout=30,
):
    print()
    print(
        f">>> {command}"
    )

    write_line(
        ser,
        command,
    )

    output, _ = read_until(
        ser,
        [IOS_PROMPT],
        timeout=timeout,
    )

    return output


def save_config(ser):

    print()
    print(
        ">>> copy running-config startup-config"
    )

    write_line(
        ser,
        "copy running-config startup-config",
    )

    end = (
        time.monotonic()
        + 60
    )

    output = ""

    while time.monotonic() < end:

        chunk = read_chunk(ser)

        if chunk:

            output += chunk

            if DEST_PROMPT.search(output):

                write_line(ser)

                output = ""
                continue

            if CONFIRM_PROMPT.search(output):

                write_line(ser)

                output = ""
                continue

            if IOS_PROMPT.search(output):

                return

        else:

            time.sleep(0.05)

    raise TimeoutError(
        "Timed out saving configuration."
    )


# ============================================================
# INTERFACE DETECTION
# ============================================================

def detect_interfaces(ser):
    """
    Detect whether ports 1/0/3-24 are primarily:
      - FastEthernet
      - GigabitEthernet

    This intentionally chooses the interface family with the
    greatest number of ports in the target range.

    Example:
        Fa1/0/1 - Fa1/0/24
        Gi1/0/1 - Gi1/0/2

    will correctly select FastEthernet.
    """

    output = ios_command(
        ser,
        "show interfaces status",
        timeout=45,
    )

    # Console syslog may split a line in "show interfaces status", e.g.
    # "Gi1/0/" followed by a log message and then "6 ...".  Supplement
    # that display with the interface declarations in the running config
    # so we never silently skip a port just because its status line broke.
    config_output = ios_command(
        ser,
        "show running-config | include ^interface",
        timeout=45,
    )

    gigabit_ports = {
        int(x)
        for x in re.findall(r"(?m)^Gi1/0/(\d+)\s", output)
    }
    fast_ports = {
        int(x)
        for x in re.findall(r"(?m)^Fa1/0/(\d+)\s", output)
    }

    # Do not anchor to the beginning of a line here; Cisco messages can
    # be inserted immediately before otherwise valid command output.
    for family, port in re.findall(
        r"interface[ \t]+(FastEthernet|GigabitEthernet)1/0/(\d+)\b",
        config_output,
        flags=re.I,
    ):
        if family.lower() == "fastethernet":
            fast_ports.add(int(port))
        else:
            gigabit_ports.add(int(port))

    gigabit_ports = sorted(gigabit_ports)
    fast_ports = sorted(fast_ports)

    candidates = []

    if gigabit_ports:
        target_gigabit = [
            port
            for port in gigabit_ports
            if TARGET_FIRST_PORT <= port <= TARGET_LAST_PORT
        ]

        candidates.append({
            "family": "GigabitEthernet",
            "short": "Gi",
            "ports": gigabit_ports,
            "target_ports": target_gigabit,
        })

    if fast_ports:
        target_fast = [
            port
            for port in fast_ports
            if TARGET_FIRST_PORT <= port <= TARGET_LAST_PORT
        ]

        candidates.append({
            "family": "FastEthernet",
            "short": "Fa",
            "ports": fast_ports,
            "target_ports": target_fast,
        })

    if not candidates:
        raise RuntimeError(
            "Could not detect FastEthernet or "
            "GigabitEthernet 1/0/x interfaces."
        )

    # Choose the interface family containing the most ports
    # in our desired 3-24 range.
    candidates.sort(
        key=lambda item: len(item["target_ports"]),
        reverse=True,
    )

    selected = candidates[0]

    if not selected["target_ports"]:
        raise RuntimeError(
            "Interfaces were detected, but there are no "
            "ports in the requested 3-24 range."
        )

    print()
    print("============================================================")
    print(" INTERFACE DETECTION")
    print("============================================================")
    print()

    if fast_ports:
        print(
            "FastEthernet ports detected: "
            + ", ".join(
                f"Fa1/0/{x}"
                for x in fast_ports
            )
        )

    if gigabit_ports:
        print(
            "GigabitEthernet ports detected: "
            + ", ".join(
                f"Gi1/0/{x}"
                for x in gigabit_ports
            )
        )

    print()
    print(
        f"Using: {selected['family']}"
    )

    print(
        "Target ports: "
        + ", ".join(
            f"{selected['short']}1/0/{x}"
            for x in selected["target_ports"]
        )
    )

    return (
        selected["family"],
        selected["short"],
        selected["ports"],
    )

# ============================================================
# CONFIG CHECK
# ============================================================

def parse_interfaces(config):

    blocks = {}

    matches = list(
        re.finditer(
            r"(?m)^interface\s+(\S+)\s*$",
            config,
        )
    )

    for index, match in enumerate(matches):

        name = match.group(1)

        start = match.end()

        if index + 1 < len(matches):

            end = matches[
                index + 1
            ].start()

        else:

            end = len(config)

        blocks[name] = (
            config[start:end]
        )

    return blocks


def check_ports(
    ser,
    family,
    available_ports,
):

    config = ios_command(
        ser,
        "show running-config",
        timeout=60,
    )

    blocks = parse_interfaces(
        config
    )

    results = {}

    for port in range(
        TARGET_FIRST_PORT,
        TARGET_LAST_PORT + 1,
    ):

        if port not in available_ports:
            continue

        interface = (
            f"{family}1/0/{port}"
        )

        block = blocks.get(interface)
        if block is None:
            raise RuntimeError(
                f"Cannot verify {interface}: interface block missing "
                "from running-config output (possibly interrupted by IOS logs)."
            )

        # On Cisco IOS, automatic negotiation is normally the default.
        # IOS often omits "speed auto" from the running configuration,
        # so a missing speed command also means the port is set to auto.
        # Fixed speeds (e.g., speed 10 or speed 100) must be corrected.
        configured_speeds = re.findall(
            r"(?m)^\s*speed\s+([^\r\n]+?)\s*$",
            block,
        )
        speed_ok = not configured_speeds or all(
            setting.strip().lower() == "auto"
            for setting in configured_speeds
        )

        portfast_ok = bool(
            re.search(
                r"(?m)^\s*spanning-tree\s+portfast(?:\s+edge)?\s*$",
                block,
            )
        )

        results[port] = {
            "interface": interface,
            "speed": speed_ok,
            "portfast": portfast_ok,
        }

    return results


def print_results(
    results,
    title,
):

    print()
    print(
        "============================================================"
    )
    print(
        f" {title}"
    )
    print(
        "============================================================"
    )

    for port in sorted(results):

        data = results[port]

        missing = []

        if not data["speed"]:

            missing.append(
                "speed auto"
            )

        if not data["portfast"]:

            missing.append(
                "portfast"
            )

        if not missing:

            print(
                f"{data['interface']:<30} PASS"
            )

        else:

            print(
                f"{data['interface']:<30} "
                f"FAIL  missing: {', '.join(missing)}"
            )


def config_is_good(results):

    return all(
        x["speed"]
        and x["portfast"]
        for x in results.values()
    )


# ============================================================
# FIX ONLY BAD SETTINGS
# ============================================================

def fix_ports(
    ser,
    results,
):

    changed = False

    ios_command(
        ser,
        "configure terminal",
    )

    for port in sorted(results):

        data = results[port]

        if (
            data["speed"]
            and data["portfast"]
        ):
            continue

        changed = True

        ios_command(
            ser,
            "interface "
            + data["interface"],
        )

        if not data["speed"]:

            ios_command(
                ser,
                "speed auto",
            )

        if not data["portfast"]:

            ios_command(
                ser,
                "spanning-tree portfast",
            )

        ios_command(
            ser,
            "exit",
        )

    ios_command(
        ser,
        "end",
    )

    if changed:

        save_config(
            ser
        )

    return changed


# ============================================================
# PASSWORD RECOVERY
# ============================================================

def wait_for_bootloader_for_recovery(
    ser,
    timeout=300,
):

    print()
    print(
        "============================================================"
    )
    print(
        " PASSWORD RECOVERY REQUIRED"
    )
    print(
        "============================================================"
    )
    print()
    print(
        "The switch finished booting, but the known password"
    )
    print(
        "was actually rejected."
    )
    print()
    print(
        "Power-cycle the switch and hold MODE until:"
    )
    print()
    print(
        "    switch:"
    )
    print()
    print(
        "appears."
    )
    print()
    print(
        "Waiting..."
    )

    end = (
        time.monotonic()
        + timeout
    )

    buffer = ""

    while time.monotonic() < end:

        chunk = read_chunk(ser)

        if chunk:

            buffer += chunk

            if BOOTLOADER_PROMPT.search(
                buffer
            ):

                print()
                print(
                    ">>> Bootloader detected"
                )

                return

            if len(buffer) > 10000:

                buffer = (
                    buffer[-10000:]
                )

        else:

            time.sleep(0.05)

    raise TimeoutError(
        "Bootloader prompt was not detected."
    )


def bootloader_command(
    ser,
    command,
    timeout=30,
):

    print()
    print(
        f">>> {command}"
    )

    write_line(
        ser,
        command,
    )

    output, _ = read_until(
        ser,
        [BOOTLOADER_PROMPT],
        timeout=timeout,
    )

    return output


def password_recovery(ser):

    wait_for_bootloader_for_recovery(
        ser
    )

    bootloader_command(
        ser,
        "flash_init",
        timeout=45,
    )

    listing = bootloader_command(
        ser,
        "dir flash:",
        timeout=45,
    )

    if "config.text" not in listing:

        raise RuntimeError(
            "flash:config.text was not found. "
            "Stopping rather than modifying flash."
        )

    if (
        "config.text.recovery"
        in listing
    ):

        raise RuntimeError(
            "flash:config.text.recovery already exists. "
            "Stopping to avoid overwriting it."
        )

    bootloader_command(
        ser,
        (
            "rename "
            "flash:config.text "
            "flash:config.text.recovery"
        ),
        timeout=45,
    )

    print()
    print(
        ">>> boot"
    )

    write_line(
        ser,
        "boot",
    )

    # THIS ALSO waits through the entire boot.
    state = wait_for_ios_ready(
        ser,
        timeout=300,
    )

    if state == "bootloader":

        raise RuntimeError(
            "Returned to bootloader instead of IOS."
        )

    # With config.text hidden, enable should work.
    if not get_privileged_mode(ser):

        raise RuntimeError(
            "Could not enter privileged mode "
            "after recovery boot."
        )

    ios_command(
        ser,
        "terminal length 0",
    )

    ios_command(
        ser,
        (
            "rename "
            "flash:config.text.recovery "
            "flash:config.text"
        ),
        timeout=45,
    )

    print()
    print(
        ">>> copy flash:config.text system:running-config"
    )

    write_line(
        ser,
        "copy flash:config.text system:running-config",
    )

    end = (
        time.monotonic()
        + 60
    )

    output = ""

    while time.monotonic() < end:

        chunk = read_chunk(ser)

        if chunk:

            output += chunk

            if DEST_PROMPT.search(output):

                write_line(ser)
                output = ""
                continue

            if CONFIRM_PROMPT.search(output):

                write_line(ser)
                output = ""
                continue

            if IOS_PROMPT.search(output):

                break

        else:

            time.sleep(0.05)

    ios_command(
        ser,
        "configure terminal",
    )

    ios_command(
        ser,
        f"enable secret {PASSWORD}",
    )

    ios_command(
        ser,
        "end",
    )

    save_config(
        ser
    )

    print()
    print(
        "Password recovery complete."
    )
    print(
        "Existing configuration was preserved."
    )

def parse_hostname(output):
    """Extract the hostname despite IOS logging interrupting a line.

    For example, some startup messages produce:
        '...administratively downhostname fragfestSwitch_5'
    A strict '^hostname' regex would miss the real configuration.
    """
    names = re.findall(
        r"hostname[ \t]+([A-Za-z0-9][A-Za-z0-9_-]*)\b",
        output,
        flags=re.I,
    )
    if names:
        return names[-1]

    # Backup: IOS privileged prompts also contain the current hostname.
    prompts = re.findall(
        r"(?m)(?:^|[\r\n])([A-Za-z][A-Za-z0-9_-]*)#(?=[ \t]*(?:\r?\n|$))",
        output,
    )
    return prompts[-1] if prompts else None


def check_hostname(ser):
    """Rename only if a *reliably detected* hostname is noncompliant."""

    current_hostname = None
    for attempt in range(2):
        output = ios_command(
            ser,
            "show running-config | include ^hostname",
            timeout=15,
        )
        current_hostname = parse_hostname(output)
        if current_hostname is not None:
            break
        print(">>> Hostname output was unclear; retrying detection...")

    # Never guess 'Switch' on a parse failure; doing so caused an
    # unnecessary rename prompt and configuration write on valid switches.
    if current_hostname is None:
        raise RuntimeError(
            "Could not reliably detect the hostname from IOS output. "
            "Skipping rename; retry after startup messages settle."
        )

    valid_hostname = re.fullmatch(
        r"fragfestSwitch_\d+",
        current_hostname,
    )

    if valid_hostname:
        print()
        print(
            f"Hostname OK: {current_hostname}"
        )
        return False

    print()
    print(
        "============================================================"
    )
    print(
        " HOSTNAME NEEDS TO BE RENAMED"
    )
    print(
        "============================================================"
    )
    print()
    print(
        f"Current hostname: {current_hostname}"
    )
    print()
    print(
        "Required format:"
    )
    print()
    print(
        "    fragfestSwitch_#"
    )
    print()

    while True:

        switch_number = input(
            "Enter switch number: "
        ).strip()

        if switch_number.isdigit():
            break

        print(
            "Please enter only the switch number."
        )

    new_hostname = (
        f"fragfestSwitch_{switch_number}"
    )

    print()
    print(
        f"Renaming:"
    )
    print(
        f"  {current_hostname}"
    )
    print(
        "       ->"
    )
    print(
        f"  {new_hostname}"
    )
    print()

    ios_command(
        ser,
        "configure terminal",
    )

    ios_command(
        ser,
        f"hostname {new_hostname}",
    )

    ios_command(
        ser,
        "end",
    )

    save_config(
        ser
    )

    print()
    print(
        f"Hostname changed to {new_hostname}"
    )

    return True

# ============================================================
# MAIN
# ============================================================

def main():

    try:

        with serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=0.1,
            bytesize=8,
            parity="N",
            stopbits=1,
        ) as ser:

            # ------------------------------------------------
            # FIRST WAIT FOR IOS TO ACTUALLY FINISH BOOTING
            # ------------------------------------------------

            state = wait_for_ios_ready(
                ser,
                timeout=300,
            )

            # If the switch was intentionally already at
            # bootloader, don't mistake it for IOS.
            if state == "bootloader":

                print()
                print(
                    "Switch is currently at the bootloader."
                )

                print(
                    "Boot IOS normally before running "
                    "the configuration checker."
                )

                sys.exit(1)

            # ------------------------------------------------
            # ONLY NOW TEST AUTHENTICATION
            # ------------------------------------------------

            authenticated = (
                get_privileged_mode(
                    ser
                )
            )

            if not authenticated:

                if not RECOVER_ON_AUTH_FAILURE:

                    raise RuntimeError(
                        "Known password was rejected."
                    )

                print()
                print(
                    "The switch is fully booted and "
                    "authentication genuinely failed."
                )

                password_recovery(
                    ser
                )

                # Re-establish normal prompt state
                # after recovery.
                write_line(ser)

                read_for(
                    ser,
                    1,
                )

                if not get_privileged_mode(
                    ser
                ):

                    raise RuntimeError(
                        "Authentication still failed "
                        "after recovery."
                    )

            # ------------------------------------------------
            # NORMAL CONFIGURATION CHECK
            # ------------------------------------------------

            ios_command(
                ser,
                "terminal length 0",
            )


            check_hostname(
                ser
            )

            (
                family,
                abbreviation,
                available_ports,
            ) = detect_interfaces(
                ser
            )

            before = check_ports(
                ser,
                family,
                available_ports,
            )

            print_results(
                before,
                "CURRENT CONFIGURATION",
            )

            if config_is_good(
                before
            ):

                print()
                print(
                    "Everything is already configured correctly."
                )

                print(
                    "No changes made."
                )

                return

            print()
            print(
                "Applying only missing settings..."
            )

            fix_ports(
                ser,
                before,
            )

            after = check_ports(
                ser,
                family,
                available_ports,
            )

            print_results(
                after,
                "FINAL VERIFICATION",
            )

            if config_is_good(
                after
            ):

                print()
                print(
                    "PASS: all required settings are correct."
                )

            else:

                print()
                print(
                    "FAIL: one or more interfaces are still incorrect."
                )

                sys.exit(2)

    except KeyboardInterrupt:

        print()
        print()
        print(
            "Interrupted by user."
        )

        sys.exit(130)

    except serial.SerialException as exc:

        print()
        print(
            f"Serial error: {exc}"
        )

        print(
            f"Make sure {SERIAL_PORT} exists "
            "and isn't open in screen."
        )

        sys.exit(1)

    except (
        TimeoutError,
        RuntimeError,
    ) as exc:

        print()
        print(
            f"ERROR: {exc}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
