#!/usr/bin/env python3
"""List and remove stale SRW boot Docker images.

Every SRW boot check tags one image per commit, so a busy Mac keeps
``srw-bot1-boot:<sha>`` and ``srw-boot-eval:<sha12>`` images forever. This
script lists the images older than a cutoff and removes them only when
``--apply`` is given. The image of the current SRW ``main`` commit and every
image a container still uses are kept. Only tags that name a commit are
considered, so a hand-made tag is never removed.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

BOOT_IMAGE_TAGS = {'srw-bot1-boot': 40, 'srw-boot-eval': 12}
DEFAULT_MAX_AGE_HOURS = 24.0
DEFAULT_SRW_REPO = Path.home() / 'Code' / 'strategy-replay-workbench'
MAIN_REFS = ('origin/main', 'main')


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True).stdout


def docker(*args, docker_bin='docker', context=None, check=True):
    command = [docker_bin] + (['--context', context] if context else [])
    return run(*command, *args, check=check)


def parse_created(value):
    """Parse a Docker timestamp such as 2026-11-10T21:02:27.123456789Z."""
    return datetime.strptime(value.strip()[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)


def main_sha(srw_repo):
    """Return the commit SHA the SRW main branch points at."""
    try:
        remote = run('git', '-C', str(srw_repo), 'ls-remote', 'origin', 'refs/heads/main').split()
        if remote:
            return remote[0]
    except (OSError, subprocess.CalledProcessError):
        pass
    for ref in MAIN_REFS:
        try:
            sha = run('git', '-C', str(srw_repo), 'rev-parse', '--verify', '--quiet', ref).strip()
        except subprocess.CalledProcessError:
            continue
        if sha:
            return sha
    raise SystemExit(f'cannot resolve the current SRW main commit in {srw_repo}')


def protected_tags(srw_repo):
    """Return the tags that name an image built from the current SRW main commit."""
    sha = main_sha(srw_repo)
    return {sha, sha[:12]}


def collect_images(docker_bin='docker', context=None):
    """Return the boot images whose tag is a commit SHA."""
    listing = docker('image', 'ls', '--no-trunc', '--format', '{{.Repository}}\t{{.Tag}}\t{{.ID}}',
                     docker_bin=docker_bin, context=context)
    images = []
    for line in listing.splitlines():
        repository, tag, identifier = line.split('\t')
        length = BOOT_IMAGE_TAGS.get(repository)
        if length and re.fullmatch(r'[0-9a-f]{%d}' % length, tag):
            images.append({'repository': repository, 'tag': tag, 'id': identifier})
    return images


def creation_times(images, docker_bin='docker', context=None):
    """Map image id to creation time and size."""
    identifiers = sorted({image['id'] for image in images})
    if not identifiers:
        return {}
    inspected = docker('image', 'inspect', '--format', '{{.Id}}\t{{.Created}}\t{{.Size}}', *identifiers,
                       docker_bin=docker_bin, context=context, check=False)
    times = {}
    for line in inspected.splitlines():
        parts = line.split('\t')
        if len(parts) != 3:
            continue
        identifier, created, size = parts
        try:
            times[identifier] = {'created': parse_created(created), 'size': int(size)}
        except ValueError:
            continue
    return times


def images_in_use(docker_bin='docker', context=None):
    """Return the ids of every image a container, running or stopped, still uses."""
    containers = docker('ps', '-aq', docker_bin=docker_bin, context=context).split()
    if not containers:
        return set()
    inspected = docker('inspect', '--format', '{{.Image}}', *containers, docker_bin=docker_bin, context=context,
                       check=False)
    return {line.strip() for line in inspected.splitlines() if line.strip()}


def plan(images, times, in_use, protected, cutoff, now):
    """Split images into the ones to prune and the ones to keep."""
    prune, keep = [], []
    for image in images:
        info = times.get(image['id'])
        if not info:
            keep.append(dict(image, reason='unknown_age'))
            continue
        entry = dict(image, **info)
        age = now - entry['created']
        entry['age_hours'] = round(age.total_seconds() / 3600, 1)
        if image['id'] in in_use:
            keep.append(dict(entry, reason='used_by_container'))
        elif image['tag'] in protected:
            keep.append(dict(entry, reason='current_main'))
        elif age < cutoff:
            keep.append(dict(entry, reason='younger_than_cutoff'))
        else:
            prune.append(entry)
    return prune, keep


def remove(images, docker_bin='docker', context=None):
    """Remove the given image tags and report the ones that failed."""
    removed, failed = [], []
    for image in images:
        reference = f"{image['repository']}:{image['tag']}"
        result = subprocess.run([docker_bin] + (['--context', context] if context else []) +
                                ['image', 'rm', reference], text=True, capture_output=True)
        if result.returncode == 0:
            removed.append(reference)
        else:
            failed.append({'reference': reference, 'error': result.stderr.strip()})
    return removed, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='remove the listed images instead of listing them')
    parser.add_argument('--max-age-hours', type=float, default=DEFAULT_MAX_AGE_HOURS)
    parser.add_argument('--srw-repo', type=Path, default=DEFAULT_SRW_REPO)
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--context', default=None, help='Docker context, for example colima-woodpecker')
    args = parser.parse_args()

    try:
        protected = protected_tags(args.srw_repo)
        images = collect_images(args.docker, args.context)
        times = creation_times(images, args.docker, args.context)
        in_use = images_in_use(args.docker, args.context)
    except (OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}), file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    cutoff = timedelta(hours=args.max_age_hours)
    prune, keep = plan(images, times, in_use, protected, cutoff, now)

    removed, failed = ([], [])
    if args.apply:
        removed, failed = remove(prune, args.docker, args.context)

    summary = {
        'mode': 'apply' if args.apply else 'dry-run',
        'max_age_hours': args.max_age_hours,
        'protected_tags': sorted(protected),
        'images_scanned': len(images),
        'to_prune': [{'reference': f"{i['repository']}:{i['tag']}", 'id': i['id'],
                      'age_hours': i.get('age_hours'), 'size_bytes': i.get('size')} for i in prune],
        'kept': [{'reference': f"{i['repository']}:{i['tag']}", 'id': i['id'],
                  'age_hours': i.get('age_hours'), 'reason': i['reason']} for i in keep],
        'removed': removed,
        'failed': failed,
    }
    print(json.dumps(summary, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
