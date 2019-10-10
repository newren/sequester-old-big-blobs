#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import stat

def decode(bytestr):
  'Try to convert bytestr to utf-8'
  return bytestr.decode('utf-8', 'backslashreplace')

def parse_args():
  parser = argparse.ArgumentParser()
  parser.add_argument('--since', metavar='RELATIVE_OR_ABSOLUTE_DATE',
                      help="Preserve large files newer than specified date")
  parser.add_argument('--size-cutoff', default='1M',
                      help="Definition of 'large' for extracting large files")
  parser.add_argument('--replace-objects', action='store_true',
                      help="Create replacement objects for old big blobs")
  parser.add_argument('refs', nargs='*', default=['--all'],
                      help="Revision specification")
  args = parser.parse_args()
  if not args.since:
    raise SystemExit("--since is required")
  if args.size_cutoff[-1] in 'KkMmGg':
    factors = {'k':10**3, 'm':10**6, 'g':10**9}
    scaling = factors[args.size_cutoff[-1].lower()]
    args.size_cutoff = int(args.size_cutoff[0:-1]) * scaling
  return args

def switch_to_toplevel():
  topdir_cmd = 'git rev-parse --show-toplevel'.split()
  topdir = subprocess.check_output(topdir_cmd).strip()
  if topdir:  # Repo may be sparse
    os.chdir(topdir)

def get_refs(ref_arguments):
  # ref_arguments might be e.g. ['--all']; we want actual list of refs
  cmd = 'git rev-parse --symbolic-full-name'.split() + ref_arguments
  return subprocess.check_output(cmd).splitlines()

def get_big_blobs(size_cutoff):
  big_ones = set()
  cmd = 'git cat-file --batch-check --batch-all-objects'.split()
  bcp = subprocess.Popen(cmd, stdout=subprocess.PIPE)
  f = bcp.stdout
  for line in f:
    sha, object_type, size = line.split()
    if object_type == b'blob' and int(size) > size_cutoff:
      big_ones.add(sha)
  return big_ones

def get_currently_used_blobs(refs):
  for rev in refs:
    cmd = 'git ls-tree -r'.split() + [rev]
    ltp = subprocess.Popen(cmd, bufsize=-1, stdout=subprocess.PIPE)
    f = ltp.stdout
    for line in f:
      sha = line.split()[2]
      yield sha

def get_recently_used_blobs(since, refs):
  cmd = ('git rev-list --since {} {}'.format(since, ' '.join(refs)) +
         ' | git diff-tree --stdin --always --root --format="" -c -r --raw')
  dtp = subprocess.Popen(cmd, shell=True, bufsize=-1, stdout=subprocess.PIPE)
  f = dtp.stdout
  for line in f:
    num = 1+len(line)-len(line.lstrip(b':'))
    oldshas = line.split()[num:2*num-1]
    for s in oldshas:
      yield s

def pack_objects(which_ones):
  # Create a new pack with just the specified objects
  cmd = 'git pack-objects big-old-objects'.split()
  pop = subprocess.Popen(cmd, bufsize=-1,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  for obj in which_ones:
    pop.stdin.write(obj + b'\n')
  pop.stdin.close()
  packname = decode(pop.stdout.read().strip())

  # Create a read-only pack-$NAME.keep file
  keepname = 'big-old-objects-%s.keep' % packname
  with open(keepname, 'bw') as f:
    pass
  st = os.stat(keepname)
  os.chmod(keepname, st.st_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)

  # Move the new packs into the .git/objects/pack directory
  git_dir_cmd = 'git rev-parse --git-dir'.split()
  git_dir = decode(subprocess.check_output(git_dir_cmd).strip())
  pack_dir = os.path.join(git_dir, 'objects', 'pack')
  shutil.move('big-old-objects-%s.pack' % packname, pack_dir)
  shutil.move('big-old-objects-%s.idx' % packname,  pack_dir)
  shutil.move('big-old-objects-%s.keep' % packname, pack_dir)

def final_gc():
  subprocess.check_call(['git', 'gc', '--aggressive', '--prune=now'])

def create_replace_refs(old_big_blobs):
  # Create replacement object
  rep_obj = b"These aren't the droids you're looking for.\n"
  cmd = 'git hash-object -w --stdin'.split()
  replacement = subprocess.check_output(cmd, input = rep_obj).rstrip()

  # Make replace refs pointing to the replacement object for each blob
  cmd = 'git update-ref --stdin'.split()
  urp = subprocess.Popen(cmd, bufsize=-1, stdin=subprocess.PIPE)
  for blob in old_big_blobs:
    urp.stdin.write(b'create refs/replace/%s %s\n' % (blob, replacement))
  urp.stdin.close()
  if urp.wait() != 0:
    raise SystemExit("Failed to prune unused refs")

def nuke_unused_refs(refs):
  import sys
  used_refs = set(refs)
  unused_refs = set()
  out = subprocess.check_output('git for-each-ref --format=%(refname)'.split())
  for ref in out.splitlines():
    if ref not in used_refs and not ref.endswith(b'/HEAD'):
      unused_refs.add(ref)

  cmd = 'git update-ref --stdin'.split()
  urp = subprocess.Popen(cmd, bufsize=-1, stdin=subprocess.PIPE)
  for ref in sorted(unused_refs):
    urp.stdin.write(b'delete %s\n' % ref)
  urp.stdin.close()
  if urp.wait() != 0:
    raise SystemExit("Failed to prune unused refs")

def main():
  switch_to_toplevel()
  args = parse_args()
  blobs_to_pack = get_big_blobs(args.size_cutoff)
  full_refs = get_refs(args.refs)
  if not args.replace_objects:
    for used in get_currently_used_blobs(full_refs):
      blobs_to_pack.discard(used)
  for used in get_recently_used_blobs(args.since, args.refs):
    blobs_to_pack.discard(used)
  print("Packing {} old, big blobs into a new pack".format(len(blobs_to_pack)))
  nuke_unused_refs(full_refs)
  if args.replace_objects:
    create_replace_refs(blobs_to_pack)
  pack_objects(blobs_to_pack)
  final_gc()

if __name__ == '__main__':
  main()
