[app]
title = NIM Chat
package.name = nimchat
package.domain = org.example
source.dir = .
source.include_exts = py,json
version = 0.1

requirements = python3,kivy,requests
orientation = portrait

android.permissions = INTERNET

# (Optional) If you want clearer text scaling:
# android.add_src =

[buildozer]
log_level = 2
warn_on_root = 1
