# 0511 Migration Note

The old "four terminals" data-collection workflow has been replaced by the
one-entry Web console workflow.

Use:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch
```

Then open:

```text
http://<robot-ip>:8000/
```

The Web page now covers:

- Manual driving.
- Cruise driving.
- Target heading control.
- Current heading zero reset.
- Current-board reconnect.
- CSV collection start/stop.
- CSV file listing and download.

For the detailed current documentation, see:

- [README.md](./README.md)
