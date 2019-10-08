TABLE OF CONTENTS
-----------------
* Purpose
* Usage
* Cheap Fake Clones


PURPOSE
-------

This is a simple script to put old, big blobs into a separate packfile
from everything else and creates a .keep file for that pack.  The
advantages to doing so are as follows:

  1) It enables cheap aggressive repacking of the small stuff.

     By keeping a .keep pack around with the really large files that
     are considered ancient, you can more easily do an aggressive
     repack of *everything else* without the heavy expense of
     delta-ing and repacking the huge files.

  2) It enables cheap, "fake" clones for continuous integration.

     Cheap fake clones are similar to shallow clones in that they
     don't have all objects, but without the atrociously negative
     workflow side-effects and without gutting debugging capability: one
     can still run `git describe` and `git log` and get useful
     information since commits and tags are included back to the root.
     Most operations work just fine; you only run into problems if you
     specifically run some operation that tries to access the old
     objects (e.g. `git log -p` and hold PageDown until you get to an
     old object, or try to run `git fsck` or clone your fake clone).
     See 'CHEAP FAKE CLONES' below for more details.

  3) It enables cheap, fake clones for very adventerous developers.

     If you request replace objects to replace the big blobs by simple
     text files, then the only git operations that fail are those that
     ignore replace objects (fsck, gc/prune, and clone/fetch of
     sufficiently old history).  The smaller repo takes up less space,
     and will even make git log -S/-G and git grep on older revisions
     run faster.

Of course, if your project is ready for a flag day to just excise the
big old objects, [git
filter-repo](https://github.com/newren/git-filter-repo) can help you
do so.  sequester-old-big-blobs only exists for those projects that
are not yet ready for a flag day rewrite of history because they need
commit ids to not change.


USAGE
-----
```
  sequester-old-big-blobs.py --since <WHEN>
                             [--size-cutoff <SIZE>]
                             [--replace-objects]
                             [-- REVS]
```

This command will place all objects larger than SIZE and older than
WHEN and reachable from REVS into a separate packfile.  It will then
prune any revisions not mentioned in REVS, and do an aggressive repack
of remaining objects.  If --replace-objects is specified, replace refs
for all the old, big objects will be created.

Examples:

1)
```
  sequester-old-big-blobs.py --since 2017-06-25 -- \
      $(git for-each-ref --format='%(refname)'
                         $(git rev-parse --symbolic-full-name HEAD HEAD@{u})
                         refs/tags/v3.1[5-9]* refs/tags/v3.[2-9]*
                         refs/remotes/origin/3.1[5-9]*
                         refs/remotes/origin/3.[2-9]*)
```

  Before this command:
```
    $ (cd .git/objects/pack && du -ms *)
    129     pack-7177d0fc85ca7cb07ad85ed32ce85557357a0ccf.idx
    9558    pack-7177d0fc85ca7cb07ad85ed32ce85557357a0ccf.pack
```

  After this command:
```
    $ (cd .git/objects/pack && du -ms *)
    1       big-old-objects-3d4f228aad746e737a9f712946f3c2f7ebd9c141.idx
    0       big-old-objects-3d4f228aad746e737a9f712946f3c2f7ebd9c141.keep
    7257    big-old-objects-3d4f228aad746e737a9f712946f3c2f7ebd9c141.pack
    117     pack-d4fd34c2ec824f552b08225b8151f8fd218268e0.idx
    1100    pack-d4fd34c2ec824f552b08225b8151f8fd218268e0.pack
```

2)
```
  sequester-old-big-blobs.py --since 2019-01-01 --size-cutoff 100k -- \
      $(git for-each-ref --format='%(refname)'
                         $(git rev-parse --symbolic-full-name HEAD HEAD@{u})
                         refs/tags/100.3019* refs/tags/100.30[2-9]*
                         refs/remotes/origin/release/3.19*
                         refs/remotes/origin/release/3.[2-9]*)
```

  Before this command:
```
    $ (cd .git/objects/pack && du -ms *)
    64      pack-9137f15ae8b793a6d296857e1ee1e983b5f82a79.idx
    1412    pack-9137f15ae8b793a6d296857e1ee1e983b5f82a79.pack
```

  After this command:
```
    $ (cd .git/objects/pack && du -ms *)
    1	    big-old-objects-f4bfd0644447b997fbfc2c0bc01eb47efae26460.idx
    0	    big-old-objects-f4bfd0644447b997fbfc2c0bc01eb47efae26460.keep
    549	    big-old-objects-f4bfd0644447b997fbfc2c0bc01eb47efae26460.pack
    34	    pack-f4ea1142bb3f5484d0d948d7ec6ab7f9352da572.idx
    359	    pack-f4ea1142bb3f5484d0d948d7ec6ab7f9352da572.pack
```


You may find `git filter-repo --analyze` helpful in picking the
--since and --size-cutoff parameters.


CHEAP FAKE CLONES
-----------------

You can create a cheap fake clone by:
  1. git clone the actual repository you want (`--no-checkout` may be useful)
  2. Run this script with appropriate paramaters, e.g.
       ```
       sequester-old-big-blobs.py --since 2016-01-01
       ```
  3. Do some cleanup:
       ```
       find .git -type d -empty -delete
       ```
  4. Create the "cloneable" archive:
       ```
         tar cf shrunk-clone.tar \
            --exclude=index --exclude=logs --exclude=info --exclude=hooks \
            --exclude=big-old-objects-* \
            .git```
(Note: Step 3 is optional, as is the first line of excludes from step 4.)

And then can use the cheap fake clone by:
  * Copy/download shrunk-clone.tar
  * `mkdir somedir`  (or `git init somedir`; doesn't matter)
  * `cd somedir`
  * `tar xf shrunk-clone.tar`
  * `git reset --hard`
