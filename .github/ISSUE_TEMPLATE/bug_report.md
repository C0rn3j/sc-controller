---
name: Bug report
about: Create a report to help us improve
title: ''
labels: bug
assignees: ''
---

<!-- Please fill out as much as you can. Leave fields empty if not applicable. -->
<!-- Text between "<!––" and "––>" will be deleted from your finalized post. -->

**Desktop<!--(please complete the following information)-->**
- OS: <!-- e.g. Arch Linux/Windows/macOS -->
- OS version: <!-- e.g. rolling/11/15.2 -->
- SCC Version: <!-- e.g. 0.7.1, see Menu->About -->
- Installation method: <!-- e.g. AppImage/OS package/from source -->

**Describe the bug**
<!-- A clear and concise description of what the bug is. -->

**To Reproduce**

Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
<!-- A clear and concise description of what you expected to happen. -->

**Screenshots/Videos**
<!-- If applicable, add screenshots/videos to help explain your problem. -->

**SCC log**
<details><summary>Logfiles</summary>
<!--
 You can launch the application via a terminal for a full log.
 To do that, you should first ensure nothing is running:
   killall -9 scc-daemon sc-controller
 Then launch the daemon:
   scc-daemon debug
 Then in a second terminal, the GUI:
   sc-controller --debug
-->

<!--
```python
 Example Python stack trace
Traceback (most recent call last):
  File "/app/bin/scc.py", line 359, in <module>
    exec(main)
  File "/app/bin/scc/scc.py", line 4333, in <module>
    auto_scale()
  File "/app/bin/scc/scc.py", line 4302, in auto_scale
    prefs.scale_want = window_size[0] / logical_size[0]
                       ~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~
ZeroDivisionError: division by zero
```
-->
