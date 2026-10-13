# Preserved KiCad save history

The project folder originally had no root Git repository. KiCad maintained a separate local repository at `hardware/kicad-readable/.history/`. Its complete existing history was copied to [kicad-save-history.bundle](kicad-save-history.bundle) during October 13, 2026 consolidation, without changing or deleting the live history.

The bundle records commit `97c31206370dae368aa45fb2a4370df6cb58571b`, branch `main`, and the `Last_Save_sch` and `Save_sch_1` tags. Git bundle verification reported complete history with no prerequisites. It is historical editor evidence, not project-wide prior commit history or a revised hardware release.

To inspect the bundle, clone it into a separate directory using `git clone path/to/kicad-save-history.bundle inspection-directory`. Keep the main working design in its existing KiCad project; do not replace current files merely to inspect historical saves.
