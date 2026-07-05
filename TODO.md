List of (possibly) planned features in no particular order:

- DualShock 4 / DualSense (ds4/ds5) polish. The HID driver is now functional
  (mapper rstick/dpad guards, touchpad coordinate scaling + click highlight), but
  rough edges remain:
    - the two analog sticks are asymmetric in Input Test -- the left and right
      stick brighten / behave differently from each other;
    - the input icons drawn around the controller are the generic ones, not the
      DualShock face symbols (cross / circle / square / triangle);
    - the DS4 gyro/IMU is unverified -- untested on the DS4 over both USB and
      Bluetooth; the decoders populate it but it has never been confirmed to work;
    - no rumble: neither DS4Controller nor DS4HidRawController drives the pad (the
      DS5 driver does) -- port the DS5/kernel output report; over Bluetooth the
      DS4HidRawController is input-only, so rumble + lightbar there need output
      reports with the BT CRC32 wrapper (mirror DS5HidRawController);
    - the lightbar LED is not driven (no DS4-specific set_led);
    - DS5 is UNVERIFIED (no DualSense hardware here): its HID touchpad scaling was
      added by analogy to the DS4 (DualSense pad assumed 1920x1080) and not tested;
      the DS5HidRawController touchpad is still unscaled and stores cpad as unsigned
      c_uint16, which can't hold the signed scaled range -- it needs a field type
      change as well as scaling.
- Multiple on-screen menus (and possibly keyboards) when using multiple controllers
- Injecting emulated xbox controller into wine
- mnuImage right-click "change background" menu has no `sc2` entry (the v2
  image is selected automatically via sc2.config.json `gui.background`, but
  it can't be picked manually from that menu yet).
- Custom small (24px) controller icons per supported controller. Today only the
  Steam Controller v1 (sc-*) and v2 (sc2-*) have bespoke top-down glyphs; every
  other type (deck, ds4, ds5, evdev, hid, scbt, fake) reuses the same generic
  silhouette, just recolored. Draw a distinct glyph per type so each controller
  is recognisable at a glance. The v2 glyph could also be refined further (its
  trackpads are necessarily small at 24px).
- Steam Controller v1 GET_SERIAL reliability (nicety). The flaky v1 serial read
  is now handled gracefully - usb.py retries a stalled control request instead of
  tearing the dongle down, and sc_dongle falls back to a generated id if it never
  reads - so multiple v1s with "Use Serial Numbers" on are detected reliably.
  Remaining nicety: investigate *why* GET_SERIAL stalls, so a v1 always ends up
  with its real serial (today a persistent stall yields a positional id instead).
- Continuous "HD rumble" for the Steam Controller v2 (and v1/Deck). The SC pads
  are LRA voice-coil actuators, not ERM spin-motors. We already drive single
  pulses (v1: FEEDBACK report 0x8F; v2: interrupt-OUT report 0x82, effect 0x01 =
  one click) which suit pad/scroll detents but NOT sustained, amplitude/
  frequency-modulated game rumble. Gap: the v2's continuous-rumble report is
  unknown (see sc2.py feedback(): "sustained game rumble may need another report,
  not yet found"); the v2 uses its own report scheme (interrupt-OUT 0x82),
  distinct from the Deck's feature-report commands, so it needs confirming for
  the v2 specifically. Approach (do NOT brute-force the HID space by trial and
  error - a wrong report just does nothing and gives no signal):
    1. Read the canonical implementations: SDL's hidapi Steam driver
       (SDL_hidapi_steam.c / SDL_hidapi_steamdeck.c - ID_TRIGGER_RUMBLE_CMD plus
       the left/right gain "magic numbers") and the Linux kernel
       drivers/hid/hid-steam.c (FF play_effect, derived from SDL's Deck code).
    2. Check first whether SDL3 already rumbles the v2 by its VID/PID - if so,
       its source *is* the v2 report format and no capture is needed.
    3. Otherwise capture ground truth: run Steam Input on the v2, trigger rumble
       (Steam's controller rumble test, or a rumbling game) and capture the USB
       OUTPUT reports with usbmon + Wireshark; decode the continuous-rumble
       report Steam actually sends.
    4. Replicate it in sc2.py feedback() and diff the emitted bytes against the
       capture to confirm.
    5. Map the emulated gamepad's FF_RUMBLE strong/weak magnitudes to the LRA's
       amplitude/frequency/gain and tune for feel (LRA != ERM, so a curve is
       needed).
  Plumbing already exists (emulated gamepad FF -> controller.feedback()); the
  missing piece is the v2 continuous-rumble report itself. Refs: SDL hidapi steam
  driver, kernel hid-steam.c, and Alice Mikhaylenko's "Steam Deck, HID, and
  libmanette adventures" writeup.
- Deck OSD menu fixes. (a) "Display Current Bindings..." and "Run Program..."
  ship disabled in the menu settings; once enabled they appear in the OSD, but
  selecting them does nothing - their shell() actions (scc-osd-show-bindings,
  scc-osd-launcher) don't actually run/work on the Deck. Make them functional.
  (b) Remove "Turn Controller OFF" from the Deck's OSD menu - the Deck's
  built-in controller can't be powered off (today it shows and does nothing).
  Entries defined in scc/gui/global_settings.py (~L45-58, e.g.
  "Turn Controller OFF" -> osd(turnoff())); menu data in
  default_menus/Default.menu.
- Generalize the OSD "Turn Controller OFF" hiding. It's currently hidden only
  for the Deck's built-in controls (controller type == "deck", checked in
  scc/osd/menu.py against the --controller-type the daemon passes). Replace that
  hardcoded type check with a per-controller capability (a ControllerFlags bit or
  a controller.can_turnoff()) so any controller that can't be powered off
  remotely hides the entry, not just the Deck.
- Deck tray/status icon not visible. On the Steam Deck the status (tray) icon
  doesn't appear even with the option enabled - works on desktop now that
  libdbusmenu is bundled, so this is a Deck/gamescope SNI-tray-host issue to
  investigate.
- Rebrand the AppImage desktop app-id. app_info.id in AppImageBuilder.yml /
  AppImageBuilder.debian.yml is still org.c0rn3j.sc-controller (upstream), so the
  installed .desktop carries the upstream id, and the after_bundle step symlinks
  it as org.c0rn3j.sc-controller.desktop. Switch both to org.patola.sc-controller-cc
  once the fork is stable and we have committed/PR'd to upstream.
- Replace the last deprecated GTK stock-icon calls. macro_editor.py (the
  up/down/delete buttons) and modeshift_editor.py (the clear button) still call
  `Gtk.Image.new_from_stock("gtk-go-up" / "gtk-go-down" / "gtk-delete", ...)`.
  They render today (GTK maps the stock id to an icon internally) but the stock
  API is deprecated; move them to `Gtk.Image.new_from_icon_name` with freedesktop
  names (go-up / go-down / edit-delete, or the -symbolic variants - all present in
  Adwaita/Breeze). Same class as the profile_switcher.py save/edit buttons, which
  were actively blank because `new_from_icon_name` was handed the stock ids
  "gtk-save"/"gtk-edit" (now document-save / document-edit).

Hard stuff:
- Injecting emulated xbox controller into PlayOnLinux

Very hard stuff:
- Visual feedback in binding editor ( [what this guy says](https://www.reddit.com/r/linux_gaming/comments/5pcdmr/sc_controller_use_steam_controller_without_steam/dcqpvf4/) )

**Done** stuff:
- "Act on release" (inverted button): a general InvertedButtonModifier plus a
  checkbox in the button action editor (next to Toggle/Repeat) that fires a
  binding on *release* instead of press - for always-on sensors like the
  capacitive grips. Round-trips with the Custom Action `inverted(...)` token.
- Dedicated v2 controller artwork: traced SVG (tools/sc2-source.svg) wired by
  tools/gen_sc2_image.py into controller-images/sc2.svg + v2 face-overlay
  glyphs (button-images/sc2_*.svg, lifted from the drawn symbols so the face
  buttons are blank in the art -> no duplication, monochrome ABXY, round Steam,
  single dots) + v2 side-panel icons (images/sc2/*.svg, per-controller override
  added in app.apply_gui_config_buttons). Control-name ids on sticks/pads/dpad/
  bumpers + grip-touch shapes so everything highlights on hover; darker body
  (#b8b8b8). sc2.config.json points at it all. Replaces the borrowed Deck image.
- Multicontroller support
- Per-controller profile memory: each controller's profile is remembered by id
  (config["controllers"][id]["profile"]) and restored on (re)connect - follows
  the physical device with "Use Serial Numbers" on, per-slot otherwise.
- Configurable gamepad type (e.g. 4 axes and 16 buttons)
- Steam Profile import
- Radial Menu for the Joystick/Trackpad
- Copy & paste
- Cycling Buttons
- Process monitor (or active window monitor) with switch
- Mouse regions
- Touch-Menu
- Menu in OSD
- OSD
- double click
- on-screen keyboard
- Spining mouse wheel rotation
- Haptic feedback support
- Gyroscope input
- Gamepad button as modifier (modeshift)
- Macros
- Turbo
- Trigger settings
- DPAD that acts only when clicked
- 8-way DPAD
- Selector for media keys