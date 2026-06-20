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