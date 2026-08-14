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
from qa_mcp.adapters.mobile import AppiumAdapter


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
