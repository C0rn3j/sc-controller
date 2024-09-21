"""SC Controller - DualSense driver.

Extends HID driver with DS5-specific options.
"""

import ctypes
import logging
import math
import os
import sys
import time
import zlib
from enum import IntEnum

from scc.constants import (
    OUTPUT_360_STICK_MAX,
    OUTPUT_360_STICK_MIN,
    OUTPUT_360_STICK_RES,
    STICK_PAD_MAX,
    STICK_PAD_MIN,
    STICK_PAD_RES,
    ControllerFlags,
    HapticPos,
    SCButtons,
)
from scc.controller import Controller
from scc.drivers.evdevdrv import (
    HAVE_EVDEV,
    EvdevController,
    get_axes,
    get_evdev_devices_from_syspath,
    make_new_device,
)
from scc.drivers.hiddrv import (
    BUTTON_COUNT,
    AxisData,
    AxisDataUnion,
    AxisMode,
    AxisModeData,
    AxisType,
    ButtonData,
    HatswitchModeData,
    HIDController,
    HIDDecoder,
    _lib,
    hiddrv_test,
)
from scc.drivers.usb import register_hotplug_device
from scc.lib.hidraw import HIDRaw
from scc.sccdaemon import SCCDaemon
from scc.tools import init_logging, set_logging_level

log = logging.getLogger("DS5")

VENDOR_ID = 0x054c
PRODUCT_ID = 0x0ce6


OPERATING_MODE_DS5_BT = 0x31

class OperatingMode(IntEnum):
    DS4_COMPATIBILITY_MODE = 1 << 0
    DS5_MODE = 1 << 1
    DS5_MODE_BT = 1 << 5 | 1 << 4 | 1 << 0


class PhysicalEffectControl(IntEnum):
    ENABLE_HAPTICS = 1 << 0 | 1 << 1
    TRIGGER_EFFECTS_RIGHT = 1 << 2
    TRIGGER_EFFECTS_LEFT = 1 << 3


class LightEffectControl(IntEnum):
    MIC_MUTE_LED_CONTROL_ENABLE = 1 << 0
    POWER_SAVE_CONTROL_ENABLE = 1 << 1
    LIGHTBAR_CONTROL_ENABLE = 1 << 2
    RELEASE_LEDS = 1 << 3
    PLAYER_INDICATOR_CONTROL_ENABLE = 1 << 4


class DualSenseHIDOutput(ctypes.Structure):
    _fields_ = [
        ('operating_mode', ctypes.c_ubyte),
        ('physical_effect_control', ctypes.c_ubyte),
        ('light_effect_control', ctypes.c_ubyte),

        ('motor_right', ctypes.c_ubyte),
        ('motor_left', ctypes.c_ubyte),

        ('unknown2', ctypes.c_ubyte * 4),
        ('mute_button_led', ctypes.c_ubyte),
        ('power_save_control', ctypes.c_ubyte),
        ('right_trigger_effect', ctypes.c_ubyte * 11),
        ('left_trigger_effect', ctypes.c_ubyte * 11),

        ('unknown3', ctypes.c_ubyte * 8),

        ('lightbar_control', ctypes.c_ubyte),
        ('lightbar_setup', ctypes.c_ubyte),
        ('led_brightness', ctypes.c_ubyte),

        ('player_leds', ctypes.c_ubyte),
        ('lightbar_red', ctypes.c_ubyte),
        ('lightbar_green', ctypes.c_ubyte),
        ('lightbar_blue', ctypes.c_ubyte),
    ]

class DualSenseHIDOutputBT(ctypes.Structure):
    _fields_ = [
        ('operating_mode', ctypes.c_byte),
        ('data_id_byte', ctypes.c_byte),
        ('physical_effect_control', ctypes.c_byte),
        ('light_effect_control', ctypes.c_byte),

        ('motor_right', ctypes.c_byte),
        ('motor_left', ctypes.c_byte),

        ('unknown2', ctypes.c_byte * 4),
        ('mute_button_led', ctypes.c_byte),
        ('power_save_control', ctypes.c_byte),
        ('right_trigger_effect', ctypes.c_byte * 11),
        ('left_trigger_effect', ctypes.c_byte * 11),

        ('unknown3', ctypes.c_byte * 6),

        ('brightlite', ctypes.c_byte),
        ('unknown6', ctypes.c_byte * 2),

        ('lightbar_control', ctypes.c_byte),
        #('lightbar_setup', ctypes.c_byte),
        ('led_brightness', ctypes.c_byte),

        ('player_leds', ctypes.c_byte),
        ('lightbar_red', ctypes.c_byte),
        ('lightbar_green', ctypes.c_byte),
        ('lightbar_blue', ctypes.c_byte),

        ('unknown4', ctypes.c_byte * 25),
        #('unknown5', ctypes.c_byte * 4),
        ('crc32', ctypes.c_byte * 4),
        #('crc32', ctypes.c_uint16),
    ]

class DualSenseHIDInputBT(ctypes.Structure):
    _fields_ = [
        ('report_id', ctypes.c_byte),
        ('unknown1', ctypes.c_byte),
        ('lx', ctypes.c_ubyte),
        ('ly', ctypes.c_ubyte),
    ]

class DualSenseBTControllerInput(ctypes.Structure):
	_fields_ = [
        ('type', ctypes.c_uint16),
        ('buttons', ctypes.c_uint32),
        ('ltrig', ctypes.c_uint8),
        ('rtrig', ctypes.c_uint8),
        ('stick_x', ctypes.c_int32),
        ('stick_y', ctypes.c_int32),
        ('lpad_x', ctypes.c_int32),
        ('lpad_y', ctypes.c_int32),
        ('rpad_x', ctypes.c_int32),
        ('rpad_y', ctypes.c_int32),
        ('accel_x', ctypes.c_int32),
        ('accel_y', ctypes.c_int32),
        ('accel_z', ctypes.c_int32),
        ('gpitch', ctypes.c_int32),
        ('groll', ctypes.c_int32),
        ('gyaw', ctypes.c_int32),
        ('q1', ctypes.c_int32),
        ('q2', ctypes.c_int32),
        ('q3', ctypes.c_int32),
        ('q4', ctypes.c_int32),
        ('cpad_x', ctypes.c_uint16),
        ('cpad_y', ctypes.c_uint16),
	]

ICON_COLORS = [
    (0.0, 1.0, 0.0),  # 0
    (0.0, 0.0, 1.0),  # 1
    (1.0, 0.0, 0.0),  # 2
    (1.0, 1.0, 0.0),  # 3
    (0.0, 1.0, 1.0),  # 4
    (1.0, 0.4, 0.0),  # 5
    (1.0, 0.0, 1.0),  # 6
]


class DS5Controller(HIDController):
    # Most of axes are the same
    BUTTON_MAP = (
        SCButtons.X,
        SCButtons.A,
        SCButtons.B,
        SCButtons.Y,
        SCButtons.LB,
        SCButtons.RB,
        1 << 64,
        1 << 64,
        SCButtons.BACK,
        SCButtons.START,
        SCButtons.STICKPRESS,
        SCButtons.RPAD,
        SCButtons.C,
        SCButtons.CPADPRESS,
    )

    flags = (ControllerFlags.EUREL_GYROS
             | ControllerFlags.HAS_RSTICK
             | ControllerFlags.HAS_CPAD
             | ControllerFlags.HAS_DPAD
             | ControllerFlags.SEPARATE_STICK
             | ControllerFlags.NO_GRIPS
             )

    def __init__(self, device, daemon, handle, config_file, config, test_mode=False):
        self._outputs = {}
        self._feedback_output = DualSenseHIDOutput(
            operating_mode=OperatingMode.DS5_MODE,
            physical_effect_control=PhysicalEffectControl.ENABLE_HAPTICS,
            motor_left=0,
            motor_right=0,
        )
        self._feedback_cancel_task = None
        super(DS5Controller, self).__init__(device, daemon, handle, config_file, config, test_mode)

    def _load_hid_descriptor(self, config, max_size, vid, pid, test_mode):
        # Overrided and hardcoded
        self._decoder = HIDDecoder()

        # Dpad works on DualSense!
        self._decoder.axes[AxisType.AXIS_LPAD_X] = AxisData(
            mode=AxisMode.HATSWITCH, byte_offset=8, size=8,
            data=AxisDataUnion(
                hatswitch=HatswitchModeData(
                    button=SCButtons.LPAD | SCButtons.LPADTOUCH,
                    min=STICK_PAD_MIN, max=STICK_PAD_MAX
                )
            )
        )

        # Sticks are the same as DS4
        self._decoder.axes[AxisType.AXIS_STICK_X] = AxisData(
            mode=AxisMode.AXIS, byte_offset=1, size=8,
            data=AxisDataUnion(
                axis=AxisModeData(
                    scale=1.0, offset=-127.5, clamp_max=257, deadzone=2
                )
            )
        )
        self._decoder.axes[AxisType.AXIS_STICK_Y] = AxisData(
            mode=AxisMode.AXIS, byte_offset=2, size=8,
            data=AxisDataUnion(
                axis=AxisModeData(
                    scale=-1.0, offset=127.5, clamp_max=257, deadzone=2
                )
            )
        )
        self._decoder.axes[AxisType.AXIS_RPAD_X] = AxisData(
            mode=AxisMode.AXIS, byte_offset=3, size=8,
            data=AxisDataUnion(
                axis=AxisModeData(
                    button=SCButtons.RPADTOUCH,
                    scale=1.0, offset=-127.5, clamp_max=257, deadzone=2
                )
            )
        )
        self._decoder.axes[AxisType.AXIS_RPAD_Y] = AxisData(
            mode=AxisMode.AXIS, byte_offset=4, size=8,
            data=AxisDataUnion(
                axis=AxisModeData(
                    button=SCButtons.RPADTOUCH,
                    scale=-1.0, offset=127.5, clamp_max=257, deadzone=2
                )
            )
        )

        # Triggers
        self._decoder.axes[AxisType.AXIS_LTRIG] = AxisData(
            mode=AxisMode.AXIS, byte_offset=5, size=8,  # Not sure about the size
            data=AxisDataUnion(
                axis=AxisModeData(
                    scale=1.0, clamp_max=1, deadzone=10
                )
            )
        )
        self._decoder.axes[AxisType.AXIS_RTRIG] = AxisData(
            mode=AxisMode.AXIS, byte_offset=6, size=8,  # Not sure about the size
            data=AxisDataUnion(
                axis=AxisModeData(
                    scale=1.0, clamp_max=1, deadzone=10
                )
            )
        )

        # Gyro
        # Leaving the AxisMode naming to match DS4
        self._decoder.axes[AxisType.AXIS_GPITCH] = AxisData(
            mode=AxisMode.DS4ACCEL, byte_offset=16
        )  # Pitch found
        self._decoder.axes[AxisType.AXIS_GROLL] = AxisData(
            mode=AxisMode.DS4ACCEL, byte_offset=20
        )  # Roll
        self._decoder.axes[AxisType.AXIS_GYAW] = AxisData(
            mode=AxisMode.DS4ACCEL, byte_offset=18
        )  # Yaw found
        self._decoder.axes[AxisType.AXIS_Q1] = AxisData(
            mode=AxisMode.DS4GYRO, byte_offset=26
        )
        self._decoder.axes[AxisType.AXIS_Q2] = AxisData(
            mode=AxisMode.DS4GYRO, byte_offset=22
        )
        self._decoder.axes[AxisType.AXIS_Q3] = AxisData(
            mode=AxisMode.DS4GYRO, byte_offset=24
        )

        # Touchpad
        self._decoder.axes[AxisType.AXIS_CPAD_X] = AxisData(
            mode=AxisMode.DS4TOUCHPAD, byte_offset=34
        )  # DualSense X
        self._decoder.axes[AxisType.AXIS_CPAD_Y] = AxisData(
            mode=AxisMode.DS4TOUCHPAD, byte_offset=35, bit_offset=4
        )  # DualSense Y

        # Button maps seem to work for standard arrangement (matching Xbox360)
        # Not enough information about the button event triggered when LT && RT are pressed?
        # Could be connected to adaptive triggers?
        self._decoder.buttons = ButtonData(
            enabled=True, byte_offset=8, bit_offset=4, size=14,  # Not sure about bit offset
            button_count=14
        )

        if test_mode:
            for x in range(BUTTON_COUNT):
                self._decoder.buttons.button_map[x] = x
        else:
            for x in range(BUTTON_COUNT):
                self._decoder.buttons.button_map[x] = 64
            for x, sc in enumerate(DS5Controller.BUTTON_MAP):
                self._decoder.buttons.button_map[x] = self.button_to_bit(sc)

        self._packet_size = 64

    def input(self, endpoint, data):
        # Special override for CPAD touch button
        if _lib.decode(ctypes.byref(self._decoder), data):
            if self.mapper:
                if data[33] >> 7:
                    # cpad is not touched
                    self._decoder.state.buttons &= ~SCButtons.CPADTOUCH
                else:
                    self._decoder.state.buttons |= SCButtons.CPADTOUCH
                self.mapper.input(
                    self,
                    self._decoder.old_state, self._decoder.state
                )

    def feedback(self, data):
        position, amplitude, period, count = data.data

        normalized_amp = float(amplitude) / 0x8000
        clamped_amp = int(normalized_amp * 0xff)
        half_amp = int(normalized_amp * 0x80)

        if position == HapticPos.LEFT:
            # NOTE: the left motor is heavier, so we must give it less oomph
            self._feedback_output.motor_left = half_amp
        elif position == HapticPos.RIGHT:
            self._feedback_output.motor_right = clamped_amp
        elif position == HapticPos.BOTH:
            self._feedback_output.motor_right = clamped_amp
            self._feedback_output.motor_left = half_amp

        duration = float(period) * count / 0x10000
        # The motors don't seem to perform reliably when shut off under 20ms
        duration = max(duration, 0.02)

        self.schedule_output('feedback', self._feedback_output)

        def clear_feedback(mapper):
            self._feedback_output.motor_right = self._feedback_output.motor_left = 0
            self.schedule_output('feedback', self._feedback_output)

        if self._feedback_cancel_task:
            self._feedback_cancel_task.cancel()
        self._feedback_cancel_task = self.mapper.schedule(duration, clear_feedback)

    def apply_config(self, config):
        icon = config['icon']
        led_level = config['led_level']
        self.configure(icon=icon, led_level=led_level)

    def configure(self, icon=None, led_level=100):
        lightbar_color = (0.0, 0.0, 1.0)  # blue by default
        if icon:
            basename, ext = icon.rsplit('.', 1)
            parts = basename.rsplit('-', 1)
            if parts:
                raw_idx = parts[-1]
                try:
                    icon_idx = int(raw_idx)
                except ValueError:
                    pass
                else:
                    if icon_idx < len(ICON_COLORS):
                        lightbar_color = ICON_COLORS[icon_idx]

        led_level_norm = float(led_level) / 100
        lightbar_color_bytes = tuple(
            int(color_norm * led_level_norm * 255)
            for color_norm in lightbar_color
        )

        output = DualSenseHIDOutput(
            operating_mode=OperatingMode.DS5_MODE,
            light_effect_control=LightEffectControl.LIGHTBAR_CONTROL_ENABLE,
            lightbar_red=lightbar_color_bytes[0],
            lightbar_green=lightbar_color_bytes[1],
            lightbar_blue=lightbar_color_bytes[2],
        )
        self.schedule_output('lightbar', output)

    def get_gyro_enabled(self):
        # Cannot be actually turned off, so it's always active
        # TODO: Maybe emulate turning off?
        return True

    def get_type(self):
        return "ds5"

    def get_gui_config_file(self):
        return "ds5-config.json"

    def __repr__(self):
        return "<DS5Controller %s>" % (self.get_id(),)

    def _generate_id(self):
        """
        ID is generated as 'ds5' or 'ds5:X' where 'X' starts as 1 and increases
        as controllers with same ids are connected.
        """
        magic_number = 1
        id = "ds5"
        while id in self.daemon.get_active_ids():
            id = "ds5:%s" % (magic_number,)
            magic_number += 1
        return id

    def schedule_output(self, output_id, output):
        self._outputs[output_id] = output

    def flush(self):
        super(DS5Controller, self).flush()

        while self._outputs:
            output_id, output = self._outputs.popitem()
            data = bytes(bytearray(output).ljust(64, b'\x00'))
            self.handle.interruptWrite(3, data)


class DS5HidRawDriver:
    def __init__(self, daemon: SCCDaemon, config: dict):
        self.config = config
        self.daemon = daemon
        daemon.get_device_monitor().add_callback("bluetooth", VENDOR_ID, PRODUCT_ID, self.make_bt_hidraw_callback, None)

    def retry(self, syspath: str):
        pass

    def make_bt_hidraw_callback(self, syspath: str, *whatever):
        hidrawname = self.daemon.get_device_monitor().get_hidraw(syspath)
        if hidrawname is None:
            return None

        #log.debug(whatever)
        try:
            dev = HIDRaw(open(os.path.join("/dev/", hidrawname), "w+b"))
            return DS5HidRawController(self, syspath, dev)
        except Exception as e:
            log.exception(e)
            return None


class DS5HidRawController(Controller):
    class _DPadOutputValues:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    """# (x, y) values
    DPAD_STATE_TYPES = {
        0: (0, STICK_PAD_MAX), # Up
        1: (STICK_PAD_MAX, STICK_PAD_MAX), # UpRight
        2: (STICK_PAD_MAX, 0), # Right
        3: (STICK_PAD_MAX, STICK_PAD_MIN), # DownRight
        4: (0, STICK_PAD_MIN), # Down
        5: (STICK_PAD_MIN, STICK_PAD_MIN), # DownLeft
        6: (STICK_PAD_MIN, 0), # Left
        7: (STICK_PAD_MIN, STICK_PAD_MAX), # UpLeft
        8: (0, 0) # Centered
    }
    """

    # (x, y) values
    DPAD_STATE_TYPES = {
        0: _DPadOutputValues(0, STICK_PAD_MAX), # Up
        1: _DPadOutputValues(STICK_PAD_MAX, STICK_PAD_MAX), # UpRight
        2: _DPadOutputValues(STICK_PAD_MAX, 0), # Right
        3: _DPadOutputValues(STICK_PAD_MAX, STICK_PAD_MIN), # DownRight
        4: _DPadOutputValues(0, STICK_PAD_MIN), # Down
        5: _DPadOutputValues(STICK_PAD_MIN, STICK_PAD_MIN), # DownLeft
        6: _DPadOutputValues(STICK_PAD_MIN, 0), # Left
        7: _DPadOutputValues(STICK_PAD_MIN, STICK_PAD_MAX), # UpLeft
        8: _DPadOutputValues(0, 0) # Centered
    }

    DPAD_CENTERED_STATE = _DPadOutputValues(0, 0)
    # Leading byte not included in sent output report data.
    # Needed to add for proper CRC32 computation that controller
    # will accept
    BT_CRC32_HEAD = b"\xA2"
    # Leading byte not included in feature report data.
    # Needed if performing CRC32 computation on returned feature
    # report data (for IMU calibration data)
    BT_CALIBRATION_CRC32_HEAD = b"\xA3"

    flags = ( ControllerFlags.EUREL_GYROS
			| ControllerFlags.HAS_RSTICK
			| ControllerFlags.HAS_CPAD
			| ControllerFlags.HAS_DPAD
			| ControllerFlags.SEPARATE_STICK
			| ControllerFlags.NO_GRIPS
	)

    #def __init__(self, device, daemon, handle, config_file, config, test_mode=False):
    def __init__(self, driver, syspath, hidrawdev):
        self.driver = driver
        self.daemon = driver.daemon
        self.syspath = syspath

        super().__init__()
        #super().__init__(device, daemon, handle, config_file, config, test_mode=False)

        self._feedback_output = DualSenseHIDOutputBT(
            operating_mode=OperatingMode.DS5_MODE_BT,
            data_id_byte = 0x02,
            physical_effect_control=PhysicalEffectControl.ENABLE_HAPTICS,
            motor_left=0,
            motor_right=0,
        )
        self._feedback_cancel_task = None
        self._outputs = {}
        # Use empty struct for starting state
        self._old_state = DualSenseBTControllerInput()

        self._device_name = hidrawdev.getName()
        self._hidrawdev = hidrawdev
        self._fileno = hidrawdev._device.fileno()
        self._id = self._generate_id() if driver else "-"
        self._previous_quat = [1.0, 0.0, 0.0, 0.0]
        self._delta_time = time.time()
        self._previous_time = time.time()

        #time.sleep(1)
        self._set_operational()
        self.read_serial()
        #self.configure()
        self._poller = self.daemon.get_poller()
        if self._poller:
            self._poller.register(self._fileno, self._poller.POLLIN, self._input)
        self.daemon.get_device_monitor().add_remove_callback(syspath, self.close)
        self.daemon.add_controller(self)

    def get_device_name(self):
        return "DualSense over Bluetooth HIDRaw"

    def get_type(self):
        return "ds5bt_hidraw"

    def apply_config(self, config):
        icon = config['icon']
        led_level = config['led_level']
        self.configure(icon=icon, led_level=led_level)

    def configure(self, icon=None, led_level=100):
        #log.debug("CALLED CONFIGURE")
        #return

        lightbar_color = (0.0, 0.0, 1.0)  # blue by default
        if icon:
            basename, ext = icon.rsplit('.', 1)
            parts = basename.rsplit('-', 1)
            if parts:
                raw_idx = parts[-1]
                try:
                    icon_idx = int(raw_idx)
                except ValueError:
                    pass
                else:
                    if icon_idx < len(ICON_COLORS):
                        lightbar_color = ICON_COLORS[icon_idx]

        led_level_norm = float(led_level) / 100
        lightbar_color_bytes = tuple(
            int(color_norm * led_level_norm * 255)
            for color_norm in lightbar_color
        )

        #print(lightbar_color_bytes)
        #lightbar_red=lightbar_color_bytes[0],
        #lightbar_green=lightbar_color_bytes[1],
        #lightbar_blue=lightbar_color_bytes[2],
        output = DualSenseHIDOutputBT(
            operating_mode=OperatingMode.DS5_MODE_BT,
            data_id_byte = 0x02,
            light_effect_control=LightEffectControl.LIGHTBAR_CONTROL_ENABLE,
            lightbar_red=lightbar_color_bytes[0],
            lightbar_green=lightbar_color_bytes[1],
            lightbar_blue=lightbar_color_bytes[2],
        )

        tempbuffer = bytearray(output)
        #print("ITS A BLUE: {}".format(output.lightbar_blue))
        self._prepare_buffer_crc(tempbuffer)
        self.schedule_output('lightbar', tempbuffer)
        #time.sleep(2)
        self.flush()
        #self._hidrawdev.read(78)
        #feature_data = self._hidrawdev.getFeatureReport(9)
        #time.sleep(2)
        #self._hidrawdev.read(78)

    def _set_operational(self):
        #log.debug("CALLING SET_OPERATIONAL")
        # Get feature report for serial performs initial switch
        # to DS5 mode
        feature_data = self._hidrawdev.getFeatureReport(9)

        init_output = DualSenseHIDOutputBT(
            operating_mode = OperatingMode.DS5_MODE_BT,
            data_id_byte = 0x02,
            light_effect_control=0x55,
            lightbar_red=0,
            lightbar_green=0,
            lightbar_blue=200,
        )

        tempman = bytearray(init_output)
        """calcCrc32 = zlib.crc32(b"\xA2") & 0xFFFFFFFF
        calcCrc32 = zlib.crc32(tempman[0:74], calcCrc32) & 0xFFFFFFFF
        tempman[74] = calcCrc32 & 0xFF
        tempman[75] = (calcCrc32 >> 8) & 0xFF
        tempman[76] = (calcCrc32 >> 16) & 0xFF
        tempman[77] = (calcCrc32 >> 24) & 0xFF
        """
        #self._hidrawdev.write(tempman)
        #time.sleep(1)
        self._prepare_buffer_crc(tempman)
        self.schedule_output("init", tempman)
        self.flush()
        # Seems to not register until the next device read. Need
        # to see if there is a way around that
        self._hidrawdev.read(78)
        #feature_data = self._hidrawdev.getFeatureReport(9)
        #time.sleep(2)

    def _prepare_buffer_crc(self, buf):
        calcCrc32 = zlib.crc32(b"\xA2") & 0xFFFFFFFF
        calcCrc32 = zlib.crc32(buf[0:74], calcCrc32) & 0xFFFFFFFF
        buf[74] = calcCrc32 & 0xFF
        buf[75] = (calcCrc32 >> 8) & 0xFF
        buf[76] = (calcCrc32 >> 16) & 0xFF
        buf[77] = (calcCrc32 >> 24) & 0xFF

    def feedback(self, data):
        position, amplitude, period, count = data.data

        normalized_amp = float(amplitude) / 0x8000
        clamped_amp = int(normalized_amp * 0xff)
        half_amp = int(normalized_amp * 0x80)

        if position == HapticPos.LEFT:
            # NOTE: the left motor is heavier, so we must give it less oomph
            self._feedback_output.motor_left = half_amp
        elif position == HapticPos.RIGHT:
            self._feedback_output.motor_right = clamped_amp
        elif position == HapticPos.BOTH:
            self._feedback_output.motor_right = clamped_amp
            self._feedback_output.motor_left = half_amp

        duration = float(period) * count / 0x10000
        # The motors don't seem to perform reliably when shut off under 50ms
        duration = max(duration, 0.05)

        tempman = bytearray(self._feedback_output)
        self._prepare_buffer_crc(tempman)
        self.schedule_output('feedback', tempman)
        self.flush()

        def clear_feedback(mapper):
            self._feedback_output.motor_right = self._feedback_output.motor_left = 0
            tempman = bytearray(self._feedback_output)
            self._prepare_buffer_crc(tempman)
            self.schedule_output('feedback', tempman)
            self.flush()

        if self._feedback_cancel_task:
            self._feedback_cancel_task.cancel()
        self._feedback_cancel_task = self.mapper.schedule(duration, clear_feedback)

    def _input(self, *a):
        #log.debug("FOUND INPUT")
        tempdata = self._hidrawdev.read(78)
        # Skip over packet if not a DS5 mode input packet
        if tempdata[0] != 0x31:
            return

        #log.debug(tempdata)
        old_state = self._old_state
        current_time = time.time()
        self._delta_time = current_time - self._previous_time
        #hamtaro = DualSenseHIDInputBT.from_buffer_copy(tempdata)
        #log.debug("LX: {} {}".format(hamtaro.lx, tempdata[2]))
        state_data = self._convert_input_data(tempdata)
        """print("INPUT [", end="")
        for index, value in enumerate(tempdata):
            print("[{},{}]".format(index, value), end=", ")

        print("")
        """

        #log.debug(self._hidrawdev._device)
        #self.flush()
        #self.close()
        if self.mapper:
            self.mapper.input(self, old_state, state_data)

        self._old_state = state_data
        # Check for pending output data
        self.flush()

        self._previous_time = current_time

    def _convert_input_data(self, data):
        state = DualSenseBTControllerInput()
        state.stick_x = self._stick_axis_scale(data[2], False)
        state.stick_y = self._stick_axis_scale(data[3], True)
        state.rpad_x = self._stick_axis_scale(data[4], False)
        state.rpad_y = self._stick_axis_scale(data[5], True)
        state.ltrig = data[6]
        state.rtrig = data[7]
        tempbyte = data[9]
        if (tempbyte & (1 << 7)) != 0:
            state.buttons |= SCButtons.Y
        if (tempbyte & (1 << 6)) != 0:
            state.buttons |= SCButtons.B
        if (tempbyte & (1 << 5)) != 0:
            state.buttons |= SCButtons.A
        if (tempbyte & (1 << 4)) != 0:
            state.buttons |= SCButtons.X
        dpad_state = data[9] & 0x0F
        if (dpad_state != 8):
            state.buttons |= SCButtons.LPAD | SCButtons.LPADTOUCH
            tempDPad = DS5HidRawController.DPAD_STATE_TYPES.get(dpad_state,
                DS5HidRawController.DPAD_CENTERED_STATE)
            state.lpad_x = tempDPad.x
            state.lpad_y = tempDPad.y

        tempbyte = data[10]
        if (tempbyte & (1 << 7)) != 0:
            state.buttons |= SCButtons.RPAD
        if (tempbyte & (1 << 6)) != 0:
            state.buttons |= SCButtons.STICKPRESS
        if (tempbyte & (1 << 5)) != 0:
            state.buttons |= SCButtons.START
        if (tempbyte & (1 << 4)) != 0:
            state.buttons |= SCButtons.BACK
        if (tempbyte & (1 << 3)) != 0:
            state.buttons |= SCButtons.RT
        if (tempbyte & (1 << 2)) != 0:
            state.buttons |= SCButtons.LT
        if (tempbyte & (1 << 1)) != 0:
            state.buttons |= SCButtons.RB
        if (tempbyte & (1 << 0)) != 0:
            state.buttons |= SCButtons.LB

        tempbyte = data[11]
        if (tempbyte & (1 << 0)) != 0:
            state.buttons |= SCButtons.C
        if (tempbyte & (1 << 1)) != 0:
            state.buttons |= SCButtons.CPADPRESS

        # Change gyro dir values to match Steam Controller
        state.gpitch = ctypes.c_int16((data[18] << 8) | data[17]).value
        state.gyaw = ctypes.c_int16((data[20] << 8) | data[19]).value * -1
        state.groll = ctypes.c_int16((data[22] << 8) | data[21]).value * -1

        # Change accel axes to match Steam Controller (flip pitch and roll)
        # Scale values for 2G instead of 1G
        state.accel_x = ctypes.c_int16((data[24] << 8) | data[23]).value * 2
        # Invert pitch
        state.accel_y = ctypes.c_int16((data[28] << 8) | data[27]).value * -2
        state.accel_z = ctypes.c_int16((data[26] << 8) | data[25]).value * 2
        #print("GYRO: {} {} {}".format(state.gyaw, state.gpitch, state.groll))
        #print("ACCEL: {} | {} | {}".format(state.accel_x, state.accel_y, state.accel_z))
        # Calculate quaternion for gyro data. Needed for tilt controls output.
        # TODO: Try to add sensor fusion and complementary filter later
        self._calculate_quaternion(state)

        # Check for CPAD touch
        if (data[34] & 0x80) == 0:
            state.buttons |= SCButtons.CPADTOUCH

        state.cpad_x = ((data[36] & 0x0F) << 8) | data[35]
        state.cpad_y = ((data[37] & 0x0F) << 4) | ((data[36] & 0xF0) >> 4)

        return state

    def _stick_axis_scale(self, value, invert=False, test=False):
        result = value - 128
        tempRatio = (result / 127.0) if (value >= 128) else (result / (128.0))
        if invert:
            tempRatio = -tempRatio

        tempRatio = (tempRatio + 1.0) * 0.5

        """if test:
            print(tempRatio)
            print("RES {}".format(STICK_PAD_RES))
            print(tempRatio * STICK_PAD_RES + STICK_PAD_MIN)
        """
        result = int(tempRatio * STICK_PAD_RES + STICK_PAD_MIN)
        return result

    def _calculate_quaternion(self, state):
        # Convert raw gyro values to degrees per second
        GYRO_RES_IN_DEG_SEC = 16
        (yaw, pitch, roll) = ((state.gyaw / GYRO_RES_IN_DEG_SEC),
            (state.gpitch / GYRO_RES_IN_DEG_SEC),
            (state.groll / GYRO_RES_IN_DEG_SEC))

        # Remove time delta element to get gyro angles and convert to radians
        old_yaw = yaw
        yaw = yaw * self._delta_time
        yaw_rad = yaw * math.pi / 180.0
        pitch = pitch * self._delta_time
        pitch_rad = pitch *  math.pi / 180.0
        roll = roll * self._delta_time
        roll_rad = roll * math.pi / 180.0
        #print("GYRO: {} {} {}".format(yaw, pitch, roll))
        #print("GYRO: {} | {} | {} | {} | {}".format(state.gyaw, old_yaw, yaw, yaw_rad, self._delta_time))

        # Obtain current quaternion
        # qx (Roll), qy (Pitch), qz (Yaw), qw (Theta)
        qx = math.sin(roll_rad/2) * math.cos(pitch_rad/2) * math.cos(yaw_rad/2) - math.cos(roll_rad/2) * math.sin(pitch_rad/2) * math.sin(yaw_rad/2)
        qy = math.cos(roll_rad/2) * math.sin(pitch_rad/2) * math.cos(yaw_rad/2) + math.sin(roll_rad/2) * math.cos(pitch_rad/2) * math.sin(yaw_rad/2)
        qz = math.cos(roll_rad/2) * math.cos(pitch_rad/2) * math.sin(yaw_rad/2) - math.sin(roll_rad/2) * math.sin(pitch_rad/2) * math.cos(yaw_rad/2)
        qw = math.cos(roll_rad/2) * math.cos(pitch_rad/2) * math.cos(yaw_rad/2) + math.sin(roll_rad/2) * math.sin(pitch_rad/2) * math.sin(yaw_rad/2)

        # Multiply previous calculated quaternion by new quaternion
        (old_qw, old_qx, old_qy, old_qz) = self._previous_quat
        Q0Q1_w = old_qw * qw - old_qx * qx - old_qy * qy - old_qz * qz
        Q0Q1_x = old_qw * qx + old_qx * qw + old_qy * qz - old_qz * qy
        Q0Q1_y = old_qw * qy - old_qx * qz + old_qy * qw + old_qz * qx
        Q0Q1_z = old_qw * qz + old_qx * qy - old_qy * qx + old_qz * qw

        # Convert normalized values to mapper expected range and store
        # in state object
        # q1 (Theta), q2 (Pitch), q3 (Roll), q4 (Yaw)
        state.q1 = int(Q0Q1_w * 32767.0)
        state.q2 = int(Q0Q1_y * 32767.0)
        state.q3 = int(Q0Q1_x * 32767.0)
        # Invert Yaw to match Steam Controller
        state.q4 = int(Q0Q1_z * -32767.0)
        # Store calculated quaternion for next poll
        self._previous_quat = [Q0Q1_w, Q0Q1_x, Q0Q1_y, Q0Q1_z]
        #print("TEST QUAT: {}".format(self._previous_quat))
        #print("TEST QUAT Z: {}".format(self._previous_quat[3] * -1))

    def close(self):
        if self._poller:
            self._poller.unregister(self._fileno)

        self.daemon.remove_controller(self)
        self._hidrawdev._device.close()
        #log.debug("CLOSING")

    def read_serial(self):
        self._serial = (self._hidrawdev
            .getPhysicalAddress().replace(b":", b""))

    def schedule_output(self, output_id, output):
        self._outputs[output_id] = output

    def flush(self):
        while self._outputs:
            output_id, output = self._outputs.popitem()
            #print("PAYLOAD {} {}".format(output_id, output))
            self._hidrawdev.write(output)
            #time.sleep(0.1)
            #print("")

        #print("SLEEPING")
        #time.sleep(0.5)

    # TODO: Remove. Temporarily keep as a reference to the nonsense
    # I went through to figure out how to compute valid CRC32 that
    # the controller would accept
    def flushni(self):
        output = []
        print(hex(zlib.crc32(b"hello-world") & 0xffffffff))

        feedback_output2 = DualSenseHIDOutputBT(
            operating_mode = 0x31,
            data_id_byte = 0x02,
            physical_effect_control = 0x0F,
            light_effect_control=0x55,
            motor_right = 0x00,
            brightlite = 0x06,
            lightbar_control = 0x02,
            led_brightness = 0x02,
            lightbar_red=200,
            lightbar_green=90,
            lightbar_blue=211,
        )

        calcCrc32 = zlib.crc32(b"\xA2") & 0xFFFFFFFF
        #calcCrc32 = ~zlib.crc32(b"\x31", calcCrc32)
        log.debug("CRC BETA")
        log.debug(calcCrc32)

        log.debug(len(bytearray(feedback_output2)[0:74]))
        damn = [int(i) for i in bytearray(feedback_output2)[0:78]]
        log.debug(damn)
        # Working
        #tempman = bytearray([0x31, 0x02, 0x0f, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x02, 0x02, 0x00, 0x14, 0x14, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        tempman = bytearray(feedback_output2)
        # Working
        #calcCrc32 = binascii.crc32(bytearray([0x31, 0x02, 0x0f, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x02, 0x02, 0x00, 0x14, 0xFF, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]), ~calcCrc32)
        #calcCrc32 = binascii.crc32(tempman[0:74], ~calcCrc32)
        calcCrc32 = zlib.crc32(tempman[0:74], calcCrc32) & 0xFFFFFFFF
        #_feedback_output.crc32 = calcCrc32
        #_feedback_output.crc32[0] = calcCrc32
        #_feedback_output.crc32[1] = calcCrc32 >> 8
        #_feedback_output.crc32[2] = calcCrc32 >> 16
        #_feedback_output.crc32[3] = calcCrc32 >> 24
        tempman[74] = calcCrc32 & 0xFF
        tempman[75] = (calcCrc32 >> 8) & 0xFF
        tempman[76] = (calcCrc32 >> 16) & 0xFF
        tempman[77] = (calcCrc32 >> 24) & 0xFF
        log.debug("CRC")
        log.debug(calcCrc32)

        print("RADIO EDIT")
        #print(bytearray(_feedback_output))
        """print("[", end="")
        for index, value in enumerate(tempman):
            print("[{},{}]".format(index, value), end=", ")

        print("")
        """

        #_test = bytes(_feedback_output)
        #_test = bytearray([0x31, 0x02, 0x0f, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x02, 0x02, 0x00, 0x14, 0x14, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        #_test[74] = calcCrc32 & 0xFF
        #_test[75] = (calcCrc32 >> 8) & 0xFF
        #_test[76] = (calcCrc32 >> 16) & 0xFF
        #_test[77] = (calcCrc32 >> 24) & 0xFF
        #print(len(_test))
        #print("THE THING {} {} {}".format(_test[40], _test[46], _test[77]))

        result = self._hidrawdev.write(tempman)
        time.sleep(0.1)
        print(result)

    def get_type(self):
        return "ds5"

    def get_gui_config_file(self):
        return "ds5-config.json"

    def _generate_id(self):
        """
        ID is generated as 'ds5' or 'ds5:X' where 'X' starts as 1 and increases
        as controllers with same ids are connected.
        """
        magic_number = 1
        id = "ds5"
        while id in self.daemon.get_active_ids():
            id = "ds5:%s" % (magic_number,)
            magic_number += 1
        return id

    def get_gyro_enabled(self):
        # Cannot be actually turned off, so it's always active
        # TODO: Maybe emulate turning off?
        return True


class DS5EvdevController(EvdevController):
    TOUCH_FACTOR_X = STICK_PAD_MAX / 940.0
    TOUCH_FACTOR_Y = STICK_PAD_MAX / 470.0
    BUTTON_MAP = {
        304: "A",
        305: "B",
        307: "Y",
        308: "X",
        310: "LB",
        311: "RB",
        # TODO: Figure out what it is the purpose of the button event when using the trigger
        # 312: "LT2",
        # 313: "RT2",
        314: "BACK",
        315: "START",
        316: "C",
        317: "STICKPRESS",
        318: "RPAD"
        # 319: "CPAD",
    }
    AXIS_MAP = {
        0: {"axis": "stick_x", "deadzone": 4, "max": 255, "min": 0},
        1: {"axis": "stick_y", "deadzone": 4, "max": 0, "min": 255},
        3: {"axis": "rpad_x", "deadzone": 4, "max": 255, "min": 0},
        4: {"axis": "rpad_y", "deadzone": 8, "max": 0, "min": 255},
        2: {"axis": "ltrig", "max": 255, "min": 0},
        5: {"axis": "rtrig", "max": 255, "min": 0},
        16: {"axis": "lpad_x", "deadzone": 0, "max": 1, "min": -1},
        17: {"axis": "lpad_y", "deadzone": 0, "max": -1, "min": 1}
    }
    # TODO: Should the old button for DS4 map be removed? DualSense support came with kernel 5.12
    # BUTTON_MAP_OLD = {
    # 	304: "X",
    # 	305: "A",
    # 	306: "B",
    # 	307: "Y",
    # 	308: "LB",
    # 	309: "RB",
    # 	312: "BACK",
    # 	313: "START",
    # 	314: "STICKPRESS",
    # 	315: "RPAD",
    # 	316: "C",
    # 	# 317: "CPAD",
    # }
    # AXIS_MAP_OLD = {
    # 	0:  { "axis": "stick_x", "deadzone": 4, "max": 255, "min": 0 },
    # 	1:  { "axis": "stick_y", "deadzone": 4, "max": 0, "min": 255 },
    # 	2:  { "axis": "rpad_x", "deadzone": 4, "max": 255, "min": 0 },
    # 	5:  { "axis": "rpad_y", "deadzone": 8, "max": 0, "min": 255 },
    # 	3:  { "axis": "ltrig", "max": 32767, "min": -32767 },
    # 	4:  { "axis": "rtrig", "max": 32767, "min": -32767 },
    # 	16: { "axis": "lpad_x", "deadzone": 0, "max": 1, "min": -1 },
    # 	17: { "axis": "lpad_y", "deadzone": 0, "max": -1, "min": 1 }
    # }
    GYRO_MAP = {
        EvdevController.ECODES.ABS_RX: ('gpitch', 0.01),
        EvdevController.ECODES.ABS_RY: ('gyaw', 0.01),
        EvdevController.ECODES.ABS_RZ: ('groll', 0.01),
        EvdevController.ECODES.ABS_X: (None, 1),  # 'q2'
        EvdevController.ECODES.ABS_Y: (None, 1),  # 'q3'
        EvdevController.ECODES.ABS_Z: (None, -1),  # 'q1'
    }
    flags = (ControllerFlags.EUREL_GYROS
             | ControllerFlags.HAS_RSTICK
             | ControllerFlags.HAS_CPAD
             | ControllerFlags.HAS_DPAD
             | ControllerFlags.SEPARATE_STICK
             | ControllerFlags.NO_GRIPS
             )

    def __init__(self, daemon, controllerdevice, gyro, touchpad):
        config = {
            'axes': DS5EvdevController.AXIS_MAP,
            'buttons': DS5EvdevController.BUTTON_MAP,
            'dpads': {}
        }
        # if controllerdevice.info.version & 0x8000 == 0:
        # 	# Older kernel uses different mappings
        # 	# see kernel source, drivers/hid/hid-sony.c#L2748
        # 	config['axes'] = DS4EvdevController.AXIS_MAP_OLD
        # 	config['buttons'] = DS4EvdevController.BUTTON_MAP_OLD
        self._gyro = gyro
        self._touchpad = touchpad
        for device in (self._gyro, self._touchpad):
            if device:
                device.grab()
        EvdevController.__init__(self, daemon, controllerdevice, None, config)
        if self.poller:
            self.poller.register(touchpad.fd, self.poller.POLLIN, self._touchpad_input)
            self.poller.register(gyro.fd, self.poller.POLLIN, self._gyro_input)

    def _gyro_input(self, *a):
        new_state = self._state
        try:
            for event in self._gyro.read():
                if event.type == self.ECODES.EV_ABS:
                    axis, factor = DS5EvdevController.GYRO_MAP[event.code]
                    if axis:
                        new_state = new_state._replace(
                            **{axis: int(event.value * factor)}
                        )
        except IOError:
            # Errors here are not even reported, evdev class handles important ones
            return

        if new_state is not self._state:
            old_state, self._state = self._state, new_state
            if self.mapper:
                self.mapper.input(self, old_state, new_state)

    def _touchpad_input(self, *a):
        new_state = self._state
        try:
            for event in self._touchpad.read():
                if event.type == self.ECODES.EV_ABS:
                    if event.code == self.ECODES.ABS_MT_POSITION_X:
                        value = event.value * DS5EvdevController.TOUCH_FACTOR_X
                        value = STICK_PAD_MIN + int(value)
                        new_state = new_state._replace(cpad_x=value)
                    elif event.code == self.ECODES.ABS_MT_POSITION_Y:
                        value = event.value * DS5EvdevController.TOUCH_FACTOR_Y
                        value = STICK_PAD_MAX - int(value)
                        new_state = new_state._replace(cpad_y=value)
                elif event.type == 0:
                    pass
                elif event.code == self.ECODES.BTN_LEFT:
                    if event.value == 1:
                        b = new_state.buttons | SCButtons.CPADPRESS
                        new_state = new_state._replace(buttons=b)
                    else:
                        b = new_state.buttons & ~SCButtons.CPADPRESS
                        new_state = new_state._replace(buttons=b)
                elif event.code == self.ECODES.BTN_TOUCH:
                    if event.value == 1:
                        b = new_state.buttons | SCButtons.CPADTOUCH
                        new_state = new_state._replace(buttons=b)
                    else:
                        b = new_state.buttons & ~SCButtons.CPADTOUCH
                        new_state = new_state._replace(
                            buttons=b,
                            cpad_x=0, cpad_y=0
                            )
        except IOError:
            # Errors here are not even reported, evdev class handles important ones
            return

        if new_state is not self._state:
            old_state, self._state = self._state, new_state
            if self.mapper:
                self.mapper.input(self, old_state, new_state)

    def close(self):
        EvdevController.close(self)
        for device in (self._gyro, self._touchpad):
            try:
                self.poller.unregister(device.fd)
                device.ungrab()
            except:
                pass

    def get_gyro_enabled(self):
        # Cannot be actually turned off, so it's always active
        # TODO: Maybe emulate turning off?
        return True

    def get_type(self):
        return "ds5evdev"

    # TODO: Create ds5-config.json for GUI
    def get_gui_config_file(self):
        return "ds5-config.json"

    def __repr__(self):
        return "<DS5EvdevController %s>" % (self.get_id(),)

    def _generate_id(self):
        """ID is generated as 'ds5' or 'ds5:X' where 'X' starts as 1 and increases as controllers with same ids are connected."""
        magic_number = 1
        id = "ds5"
        while id in self.daemon.get_active_ids():
            id = "ds5:%s" % (magic_number,)
            magic_number += 1
        return id


def init(daemon, config):
    """Register hotplug callback for DS5 device."""

    def hid_callback(device, handle):
        return DS5Controller(device, daemon, handle, None, None)

    def make_evdev_device(syspath: str, *whatever):
        devices = get_evdev_devices_from_syspath(syspath)
        # With kernel 4.10 or later, PS4 controller pretends to be 3 different devices.
        # 1st, determining which one is actual controller is needed
        controllerdevice = None
        for device in devices:
            count = len(get_axes(device))
            if count == 8:
                # 8 axes - Controller
                controllerdevice = device
        if not controllerdevice:
            log.warning("Failed to determine controller device")
            return None
        # 2nd, find motion sensor and touchpad with physical address matching controllerdevice
        gyro, touchpad = None, None
        phys = device.phys.split("/")[0]
        for device in devices:
            if device.phys.startswith(phys):
                axes = get_axes(device)
                count = len(axes)
                if count == 6:
                    # 6 axes
                    if EvdevController.ECODES.ABS_MT_POSITION_X in axes:
                        # kernel 4.17+ - touchpad
                        touchpad = device
                    else:
                        # gyro sensor
                        gyro = device
                    pass
                elif count == 4:
                    # 4 axes - Touchpad
                    touchpad = device
        # 3rd, do a magic
        if controllerdevice and gyro and touchpad:
            return make_new_device(DS5EvdevController, controllerdevice, gyro, touchpad)

    def fail_cb(syspath: str, vid: int, pid: int):
        if HAVE_EVDEV:
            log.warning(
                "Failed to acquire USB device, falling back to evdev driver. This is far from optimal."
                )
            make_evdev_device(syspath)
        else:
            log.error(
                "Failed to acquire USB device and evdev is not available. Everything is lost and DS5 support disabled."
                )
        # TODO: Maybe add_error here, but error reporting needs little rework so it's not threated as fatal
        # daemon.add_error("ds5", "No access to DS5 device")

    if config["drivers"].get("hiddrv") or (HAVE_EVDEV and config["drivers"].get("evdevdrv")):
        register_hotplug_device(hid_callback, VENDOR_ID, PRODUCT_ID, on_failure=fail_cb)
        if config["drivers"].get("hiddrv"):
            # Only enable HIDRaw support for BT connections if hiddrv is enabled
            _drv = DS5HidRawDriver(daemon, config)
        elif HAVE_EVDEV and config["drivers"].get("evdevdrv"):
            # Attempt evdev as a backup
            daemon.get_device_monitor().add_callback(
                "bluetooth",
                VENDOR_ID, PRODUCT_ID, make_evdev_device, None,
            )
        return True
    else:
        log.warning("Neither HID nor Evdev driver is enabled, DS5 support cannot be enabled.")
        return False


if __name__ == "__main__":
    """ Called when executed as script """
    init_logging()
    set_logging_level(True, True)
    sys.exit(hiddrv_test(DS5Controller, ["054c:0ce6"]))
