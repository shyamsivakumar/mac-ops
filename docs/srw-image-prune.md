# SRW boot image prune (MO-160)

Every SRW boot check builds one image per commit, so a busy Mac keeps
`srw-bot1-boot:<sha>` and `srw-boot-eval:<sha12>` images forever. The prune
script lists the stale ones and removes them only when `--apply` is given.

## What it considers

The script looks only at the `srw-bot1-boot` and `srw-boot-eval`
repositories, and only at tags that name a commit: the full SHA for
`srw-bot1-boot` and the twelve character prefix for `srw-boot-eval`. Any other
tag is ignored and is never removed.

## What it keeps

An image is kept when a container still uses it, when its tag names the
current SRW `main` commit in either form, or when it is younger than the
cutoff. The current `main` commit is read from `origin/main` over the
network. A local ref can be behind the remote, so the script stops and
removes nothing when the remote cannot be reached. The cutoff is 24 hours by
default.

The script also stops and removes nothing when it cannot inspect every
container, because an incomplete list of containers in use would hide an
image that must be kept.

## Run a scan

```sh
python3 scripts/srw_image_prune.py
```

The default run is a dry run that prints JSON: the images to prune with their
age and size, every kept image with the reason it was kept, the protected
tags, and the images that were removed.

## Remove the stale images

```sh
python3 scripts/srw_image_prune.py --apply
```

`--apply` removes the listed images and reports every image that failed, so
a partial removal is visible. `--max-age-hours` changes the cutoff,
`--srw-repo` points at another SRW checkout, and `--context` selects another
Docker context for a VM-based engine.

The script never removes an image a container uses, never removes the image of
the current `main`, and never removes a tag that does not name a commit. It
does not touch any other image, and it leaves the boot images of the last 24
hours alone. When it cannot prove that a removal is safe, it removes nothing
and exits non-zero. The daily disk hygiene job for the CI host keeps its own
rule of pruning dangling images only, so it is not the owner of these tags.
