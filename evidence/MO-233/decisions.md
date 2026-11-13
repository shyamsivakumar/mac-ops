# MO-233 decisions

Run id: `ticket:shyamsivakumar/mac-ops#226:a1`. Refs #226.

## What landed

- `coordinator/pi/bin/kpane`: the diagram popup. It shows the picture in a
  Herdr overlay near the full window, drawn by the new `kpane` mod.
- `coordinator/mods/kpane`: that mod. It draws the picture, its title and the
  zoom buttons; Esc closes it.
- `coordinator/pi/bin/kshow`: the kitty-graphics picture, moved here from
  `~/.local/bin`.
- `coordinator/pi/bin/coord-ask`: usage on `-h`, `--help` and no arguments,
  and it never sends a message that starts with `-`.
- `install_coordinator.py`: `kpane` and `kshow` install with the other pi
  coordinator files; the `kpane` mod installs with the other mods. The old
  `~/.local/bin/kpane` and `~/.local/bin/kshow` are kept as backups by the
  installer, so a revert is an install again.
- `evidence/MO-233/kpane-popup-fit.png` and `kpane-popup-zoom2.png`: the
  popup at its default size and at twice the size.

No existing test was edited or weakened. No new test file was added, as the
brief says.

## Why a Herdr overlay and not a Preview window

Both were built and run on this Mac. A Preview window opens, but Herdr's
window stays above it: Preview came to the front (the menu bar changed to
Preview) and its window was still behind the coordinator window, so the
picture was not there to be seen. That is the same miss the side pane
caused. The overlay is drawn by Herdr itself, over the layout, so it is
always on top and always where Shyam is looking. It also closes with Esc
and needs no new app.

A Preview window stays as the fallback when there is no Herdr to draw the
overlay: `kpane` opens the picture with `open -a Preview` then.

## How the picture gets to the mod

`kpane` writes the picture and a small pointer file into
`~/.config/herdr-app/kpane/` and opens the overlay with `herdr-app do
mod.open --name kpane`. The pointer says which picture to show, its title,
its size and its zoom. The mod reads the pointer, so it does not have to
read the picture itself.

The path is relative to the Herdr app home on purpose: `image()` in a mod
resolves against that directory and reads nothing else. An absolute path
does not work; that was tried first and the picture stayed blank.

`mod.open` toggles, so a second `kpane` would close the popup instead of
showing the new picture. `kpane` looks at `herdr-app status` first: when
the popup is already open it closes it, waits half a second and opens it
again.

## The zoom

Shyam asked for a popup he can "expand and look at". The popup is near the
full window and the picture fills it, so the whole diagram is there by
default. To look at part of it, the header has `-`, `Fit` and `+` (and the
scroll wheel works): the picture is drawn larger and the popup scrolls.
`kpane <file> <title> <zoom>` starts at that zoom, so `kpane diagram.svg
"Queue map" 2` opens it at twice the size.

## The stray `--help`

`kpane --help` opened a pane with a Python traceback and `coord-ask
--help` sent `--help` to the coordinator as if Shyam had written it from
the phone. Both now print usage and stop:

- `kpane --help`, `kpane` with no arguments, `kpane` on a file that is not
  there, `kshow` the same way: usage and exit 1.
- `coord-ask --help` and `coord-ask` with no arguments: usage and exit 1.
- `coord-ask -x`: usage, exit 1, and nothing is sent. The message would
  have started with `-`, so it is refused before the coordinator is even
  looked up. The proof is that the coordinator terminal's screen did not
  change and no session file holds `From Shyam (phone): -x`.

`coord-ask --last` and a normal message are untouched.

## Not changed

The diagram content, the coordinator prompt rules and the phone relay are
not touched. `coord-ask`'s normal send and `--last` are not touched.
