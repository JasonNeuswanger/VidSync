# VidSync — moved

**This repository has been replaced by [JasonNeuswanger/vidsync-free](https://github.com/JasonNeuswanger/vidsync-free).**

Development of the free, open-source VidSync 1.x line continues there. Please update your remote:

```bash
git remote set-url origin https://github.com/JasonNeuswanger/vidsync-free.git
```

This repository is kept, archived and unchanged, so that existing clones and any commit SHA
referenced elsewhere remain valid. It receives no further updates.

## Why the move

An Xcode `DerivedData` directory was committed at one point and later removed from the tree, but
it remained in history — about 1.2 GB of precompiled headers and build products that every clone
had to download. Removing it required rewriting history, which would have invalidated every commit
SHA in this repository. Publishing the cleaned history as a new repository leaves this one intact
for anyone depending on it.

`vidsync-free` has identical file content at the 1.81 release, tagged `v1.81`, with the build
artifacts stripped from history.

## About VidSync

VidSync measures the 3D positions and movements of fish and their physical habitats from
synchronized stereo video. See [vidsync.org](https://www.vidsync.org).

Neuswanger, J.R., Wipfli, M.S., Rosenberger, A.E., and Hughes, N.F. (2016). Measuring fish and
their physical habitats: versatile 2D and 3D video techniques with user-friendly software.
*Canadian Journal of Fisheries and Aquatic Sciences* 73(12): 1861–1873.
