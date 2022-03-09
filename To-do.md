#  VidSync to-do list

## Debugging

* Portraits need to be completely redone
* Left and right aren't always synced perfectly after play/pause with arrow keys

## Minor debugging

* Progress indicators don't work for video capture. The "recalculate calibration" progress indicator might also not be working right.
* Text on the add new clip panel is black too
* When "show advanced controls with only one clip loaded" setting is on, and you go to add two new clips ot a new project, the first one doesn't show its playback controls to
allow synchronizing. Need to uncheck that setting to work normally with 2 clips.
* Set as master button needs updated look
* Sync lock with Brandon's calib videos, with left as master, gave +24 hours -8 seconds sync when it should have just given -8 seconds; got it to work switching masters and getting +8
* Using Brandon's 4K videos (especially left camera), it was really hard to get chessboard corner detection to actually find the corners. I could limit points by either quantity or 
  quality threshold, and either way most of the detected points (including the "best" detected points) simply weren't on chessboard corners at all. Very strange!
* Playback controls don't return to where they were when last closed/used.
* Possible crash bug clicking calibration points, only sometimes, and possibly only when option-clicking to snap.
* Default new object colors may be blank?
* The default types don't have connecting line length labeled for length measurements
* Add annotation button style


## Feature improvements

* Improve initial window layout
* Add a preset for 10 % size for 4K videos on smaller screens.
* Add "random bright color" or "random dark color" options for object creation

## Efficiency improvements

* Use the method here to make formatters static https://stackoverflow.com/questions/554969/using-static-keyword-in-objective-c-when-defining-a-cached-variable

## Documentation improvements

* The distortion correction webpage is largely empty except for a link to automatic plumbline detection.

## Change log for users

* The app works for the latest MacOS
* Control styles (buttons etc) have been changed to look better with current MacOS design themes, both light and dark mode.



