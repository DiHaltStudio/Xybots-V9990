# openMSX start-up for `make run`: show the GFX9000 output (the MSX VDP is blanked by the port). The video source can only be selected once
# the machine has registered it, hence the deferred command.
after boot { catch { set videosource GFX9000 } }
after time 1 { catch { set videosource GFX9000 } }
