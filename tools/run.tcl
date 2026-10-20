# Show the native MSX credits/detection first, then the V9990 logo/opening.
# C500h is the RAM opening entry, reached after the banner's 120-frame wait.
after boot { catch { set videosource MSX } }
set ::xybots_opening_bp [debug set_bp 0xc500 {} {
    catch { set videosource GFX9000 }
    debug remove_bp $::xybots_opening_bp
    unset ::xybots_opening_bp
}]
