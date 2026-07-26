# OpenCV framework

VidSync links `OpenCV/opencv2.framework` — a **static**, universal
(`x86_64` + `arm64`) build of **OpenCV 4.14.0**, minimum macOS 12.0.

## You do not need to build this

The framework is committed, with its 199 MB binary stored in Git LFS. A normal
clone gives you a working framework:

```sh
git clone https://github.com/JasonNeuswanger/VidSync.git
```

Git LFS must be installed first (`brew install git-lfs && git lfs install`).
If you cloned before installing it, run `git lfs pull`.

To check that the binary is real rather than a leftover pointer:

```sh
file OpenCV/opencv2.framework/Versions/A/opencv2
# Mach-O universal binary with 2 architectures: [x86_64] [arm64]
```

If that prints ASCII text beginning `version https://git-lfs.github.com/...`,
you have the pointer, not the binary — run `git lfs pull`.

## Why is it called "opencv2" when this is OpenCV 4?

`opencv2` is the framework's historical product name, unchanged since OpenCV
2.x, and OpenCV's own build script still defaults `--framework_name` to it. The
umbrella header is `<opencv2/opencv.hpp>` regardless of major version. The
version inside is genuine 4.14.0 — see `Versions/A/Headers/core/version.hpp`.

## Rebuilding (only needed to change version or architectures)

Requires cmake ≥ 4.0 and full Xcode (not just Command Line Tools):

```sh
git clone --branch 4.14.0 https://github.com/opencv/opencv.git /tmp/opencv_4140
cd /tmp/opencv_4140 && git checkout -b build-4140   # script rejects detached HEAD

DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
python3 /tmp/opencv_4140/platforms/osx/build_framework.py \
  --macos_archs "x86_64,arm64" --build_only_specified_archs \
  --macosx_deployment_target 12.0 --legacy_build --disable-swift \
  ~/Documents/opencv-build
```

Then replace `OpenCV/opencv2.framework` with the result. `--legacy_build` pins
`--framework_name=opencv2 --without=objc`, which is what keeps the name and
import paths stable; it also means the Objective-C wrapper headers (`AKAZE.h`,
`ANN_MLP.h`, …) are absent. VidSync never used them.

Delete the `Modules` symlink afterwards — this build produces no `Modules`
directory, so it dangles.

## What VidSync actually uses

Only `core`, `imgproc`, and `imgcodecs`:

| Symbol | Module |
|---|---|
| `cv::Mat`, `cv::Point2f`, `cv::Size`, `cv::TermCriteria`, `cv::Exception`, `cv::noArray` | core |
| `cv::goodFeaturesToTrack`, `cv::cornerSubPix`, `cv::COLOR_BGR2GRAY` | imgproc |
| `CGImageToMat` (via `opencv2/imgcodecs/macosx.h`) | imgcodecs |

A build restricted to those three modules would be considerably smaller, but it
would need the `#import <opencv2/opencv.hpp>` umbrella includes in the six
source files that use OpenCV replaced with per-module headers, since the
umbrella pulls in headers for modules that would no longer exist.
