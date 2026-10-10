"""Pygame front-end. Run with `python -m chaos_blackjack.gui`.

Layout:
  app.py        window, main loop, canvas scaling, shared services
  scene.py      Scene base class, @register_scene, SceneManager (stack)
  widgets.py    Label / Button / Toggle / WidgetGroup
  assets/       manifest of known art, procedural placeholders, AssetManager
  scenes/       one module per screen
  theme.py      palette and font sizes
  settings.py   window + asset search dirs (CHAOS_ASSETS_DIR overrides)
"""
