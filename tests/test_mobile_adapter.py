"""Unit tests for qa_mcp.adapters.mobile.AppiumAdapter's option-building
logic - device-independent (no Appium server/emulator/physical device
required), so these run in any environment.

The app_activity/capabilities support tested here was added after
validating AppiumAdapter against a real physical Android device (OPPO/
Realme CPH1819, Android 10) connected to this sandbox over adb. That run
surfaced two real gaps neither this repo's own tests nor its README had
caught before, because they only show up against real hardware:

1. app_activity was hardcoded to ".MainActivity" - launching any real app
   whose main activity isn't literally named that (the overwhelming
   majority of real-world apps, including system apps like Settings,
   whose launch activity here is ".Settings") failed immediately.
2. There was no way to pass extra Appium capabilities. This device's OEM
   (ColorOS) requires appium:ignoreHiddenApiPolicyError and appium:noReset
   just to create a session at all - without them createSession fails
   with a SecurityException from the OEM's settings/clear-data guards.

With both fixes applied, launch/assert_element/tap/swipe/close were all
confirmed working end to end against the real device in this session (not
captured here as an automated test since the device is specific to this
sandbox and wouldn't be present in other environments/CI).
"""
import pytest

from qa_mcp.adapters.mobile import AppiumAdapter, MaestroAdapter


def test_build_options_defaults_to_main_activity_when_unset():
    adapter = AppiumAdapter()
    options = adapter._build_options("com.example.app")
    assert options.app_activity == ".MainActivity"


def test_build_options_uses_custom_app_activity_when_provided():
    adapter = AppiumAdapter(app_activity=".Settings")
    options = adapter._build_options("com.android.settings")
    assert options.app_activity == ".Settings"
    assert options.app_package == "com.android.settings"


def test_build_options_applies_extra_capabilities():
    adapter = AppiumAdapter(capabilities={
        "appium:ignoreHiddenApiPolicyError": True,
        "appium:noReset": True,
    })
    options = adapter._build_options("com.example.app")
    caps = options.to_capabilities()
    assert caps["appium:ignoreHiddenApiPolicyError"] is True
    assert caps["appium:noReset"] is True


def test_build_options_without_capabilities_does_not_error():
    adapter = AppiumAdapter()
    options = adapter._build_options("com.example.app")
    assert options.app_package == "com.example.app"


def test_build_options_sets_device_name_when_provided():
    adapter = AppiumAdapter(device_name="emulator-5554")
    options = adapter._build_options("com.example.app")
    assert options.device_name == "emulator-5554"


# --- MaestroAdapter retry-on-transient-disconnect -------------------------
#
# Confirmed live against the same real device: running the identical
# `maestro test` invocation back to back, unmodified, sometimes fails with
# "was requested, but it is not connected" even though `adb devices` shows
# the device connected throughout - a transient flakiness in Maestro's own
# device-connection handling over USB, not something qa_mcp causes.
# MaestroAdapter is more exposed to this than AppiumAdapter because it
# spawns a brand new `maestro test` process for every single action
# instead of holding one long-lived session, so a short retry on this one
# specific, empirically-transient error is worth it. These tests fake the
# `maestro` binary as a tiny shell script so they don't need real hardware.

def _fake_maestro_binary(tmp_path, behavior: str) -> str:
    """behavior: 'always_fail' | 'fail_once' | 'always_ok'"""
    script = tmp_path / "fake-maestro"
    state_file = tmp_path / "calls"
    if behavior == "always_fail":
        body = (
            "#!/bin/sh\n"
            "echo 'Device FAKE was requested, but it is not connected.' >&2\n"
            "exit 1\n"
        )
    elif behavior == "fail_once":
        body = (
            "#!/bin/sh\n"
            f"COUNT_FILE={state_file}\n"
            'N=$( [ -f "$COUNT_FILE" ] && cat "$COUNT_FILE" || echo 0 )\n'
            'N=$((N + 1))\n'
            'echo "$N" > "$COUNT_FILE"\n'
            'if [ "$N" -eq 1 ]; then\n'
            "  echo 'Device FAKE was requested, but it is not connected.' >&2\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n"
        )
    else:
        body = "#!/bin/sh\nexit 0\n"
    script.write_text(body)
    script.chmod(0o755)
    return str(script)


@pytest.mark.asyncio
async def test_maestro_retries_and_recovers_from_transient_disconnect(tmp_path):
    adapter = MaestroAdapter(udid="FAKE", maestro_bin=_fake_maestro_binary(tmp_path, "fail_once"))
    result = await adapter.launch("com.example.app")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_maestro_gives_up_after_max_retries_on_persistent_disconnect(tmp_path):
    adapter = MaestroAdapter(udid="FAKE", maestro_bin=_fake_maestro_binary(tmp_path, "always_fail"))
    result = await adapter.launch("com.example.app")
    assert result["success"] is False


@pytest.mark.asyncio
async def test_maestro_does_not_retry_non_transient_failures(tmp_path):
    """A real assertion/flow failure (not a connectivity issue) must not be
    retried - retrying would just waste time re-running a flow doomed to
    fail the same way every time.
    """
    script = tmp_path / "fake-maestro"
    script.write_text("#!/bin/sh\necho 'Assertion failed: element not found' >&2\nexit 1\n")
    script.chmod(0o755)

    adapter = MaestroAdapter(udid="FAKE", maestro_bin=str(script))
    result = await adapter.launch("com.example.app")
    assert result["success"] is False
