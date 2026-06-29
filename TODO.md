List of (possibly) planned features in no particular order:

- Multiple on-screen menus (and possibly keyboards) when using multiple controllers
- Remember each controller's profile across (re)connects. Today a controller
  always loads the global default (recent_profiles[0]) on connect; the per-
  controller config (config["controllers"][id]) stores name/icon/LED/etc. but no
  profile. Add a "profile" key there, persist it from the daemon's "Profile:"
  handler for *explicit* user selections only (exclude the autoswitch daemon and
  .mod/.scc-osd temp profiles), and load it in add_controller - overriding the
  reused pooled-mapper leftover and falling back to the global default. Keyed by
  controller id, so it follows the physical device only with "Use Serial Numbers"
  on (per-slot / connection-order otherwise).
- Injecting emulated xbox controller into wine
- "Touch" tab in the stick/pad action editor (next to Press / Hold /
  Double-click) to bind the capacitive stick-touch sensor, instead of exposing
  it on the main controller image.
- mnuImage right-click "change background" menu has no `sc2` entry (the v2
  image is selected automatically via sc2.config.json `gui.background`, but
  it can't be picked manually from that menu yet).
- LT/RT/GYRO side-panel icons still use the shared defaults (look fine; not
  flagged). The rear paddles now use dedicated v2 oval icons (L4/R4/L5/R5,
  from tools/sc2-assets/) and grip-touch shows both on the controller face
  (curved surface, green on hover) and in the side-panel grid.
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
- Deck tray/status icon not visible. On the Steam Deck the status (tray) icon
  doesn't appear even with the option enabled - works on desktop now that
  libdbusmenu is bundled, so this is a Deck/gamescope SNI-tray-host issue to
  investigate.

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