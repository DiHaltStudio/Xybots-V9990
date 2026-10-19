# `make run2`: like `make run`, plus openMSX's joystick 2 in port B for player 2 (a host gamepad, openMSX's default msxjoystick2
# bindings). Player 2 also has the MSX keyboard (ADR-037): W A S D move, CTRL fires, SHIFT + A / D turns.
source [file join [file dirname [info script]] run.tcl]
plug joyportb msxjoystick2
