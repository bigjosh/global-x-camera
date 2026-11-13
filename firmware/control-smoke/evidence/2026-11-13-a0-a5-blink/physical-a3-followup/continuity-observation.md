# A3 to direct PA2 tap has continuity

The user reports A3/CN4.4 to CN3.34 is **effectively0ohm** with power removed.
Together with all A contacts reading approximately1Mohm to ground, this
rules against an openSB6 or simple hard short as the explanation. It does
not establish the continuity of the inaccessible U21 ballT8 connection.

The next test is to put PA2 in inputmode with an internal pull-up, leaving
the other five pins blinking. The existing loop changes only BSRR after
initialization, so it will not override the inputmode. RM0486 section15.3.9
specifies that inputmode disables the strong driver and enables the selected
PUPDR pull; DS14791 Table67 specifies30–50kohm pull resistance. A healthy
path against the roughly1Mohm external load should rise near3.1–3.2V.

User reconnection of direct5V/ST-LINK has been requested and is pending.
No live changes have yet been made. Save/restore only PA2 MODER/PUPDR fields;
do not operate the bench before ready confirmation. This is an electrical
diagnostic, not a new normal firmware or a change of canonical HOLD pin.
