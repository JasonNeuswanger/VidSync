# modelconvert — Core Data model format conversion and verification

VidSync's Core Data model (`VidSyncProject.xcdatamodeld`) began life in the
Xcode 3 era, when each model version was stored as a binary plist (`elements` +
`layout` files) that only Xcode's GUI editor could modify. In August 2026 the
**current** version was converted to the modern XML source format (a single
`contents` file), which is plain text — readable, diffable, and directly
editable. The 30+ historical versions remain in the binary format on purpose:
they are frozen migration sources that never need editing again, and leaving
them untouched guarantees their compiled version hashes cannot change.

## Tools

- `convert_mom_to_xml.swift` — converts a *compiled* model (`.mom`) to modern
  XML source (`contents`). Works from the compiled model because that is the
  authoritative schema, readable through documented Core Data API. Hard-fails
  on any model feature it doesn't explicitly handle.
- `verify_models.swift` — exhaustively compares two compiled `.mom` files:
  entity version hashes (which determine store compatibility and migration
  behavior) plus every schema detail hashes don't cover (delete rules, class
  names, defaults, validation, renaming identifiers, indexes, userInfo...).
  Exits 0 only if identical.
- `convert_current_version.sh` — driver. Compiles the bundle, converts the
  current version, recompiles, verifies the conversion, and confirms every
  historical version still compiles byte-identically. Dry-run by default;
  `--install` swaps the verified XML into the bundle.

momc lives inside Xcode.app (not the Command Line Tools); the driver defaults
to `/Applications/Xcode.app/Contents/Developer/usr/bin/momc`, overridable via
the `MOMC` env var.

## Known intentional differences from the binary-format compile

- Legacy Sync Services userInfo entries (`com.apple.syncservices.Syncable = NO`,
  scattered through the old model) are gone: modern momc strips them from
  XML-format models. Sync Services died with OS X 10.8 and nothing in VidSync
  reads them. Not part of version hashes.
- Indexes derived from legacy `indexed="YES"` flags get different *names* from
  momc depending on source format (`startTimecode` vs `byStartTimecodeIndex`).
  The indexed columns are identical; index names are not part of version hashes
  and do not affect existing stores.

Neither difference affects entity version hashes — all 20 matched exactly at
conversion time — so existing documents open with no migration at all.

## How to make a schema change now

1. **Snapshot** the current version: copy the whole
   `VidSyncProject.xcdatamodel` directory to `VidSyncProject 1.NN.xcdatamodel`
   (next number), and register the copy in `VidSync.xcodeproj/project.pbxproj`
   (one `PBXFileReference` plus one child entry in the `XCVersionGroup`
   section — copy the pattern from version 1.34). Or use Xcode's
   Editor → Add Model Version, which does both.
2. **Edit** `VidSyncProject.xcdatamodeld/VidSyncProject.xcdatamodel/contents`
   directly (it's XML), and update the corresponding `NSManagedObject`
   subclass (`@property` declarations in the `.h`, `@dynamic` in the `.m`).
3. **Lightweight migration limits**: adding/removing attributes,
   relationships, and entities is handled automatically at document open
   (`VidSyncDocument.mm` sets `NSMigratePersistentStoresAutomaticallyOption` +
   `NSInferMappingModelAutomaticallyOption`). A *rename* must carry
   `elementID="oldName"` on the renamed element or old documents will treat it
   as delete+add and lose the data (see the eight `elementID` attributes on
   VSCalibration from the quadrat→calibrationFrame renames). Anything that
   must *transform* data needs a custom mapping model or a post-open fixup.
4. **Sanity-check** by compiling: `momc VidSyncProject.xcdatamodeld /tmp/out.momd`
   (errors mean malformed XML; warnings about missing inverses etc. mirror
   Xcode's). To confirm an edit didn't accidentally change unrelated entities,
   compile before and after and run
   `swift verify_models.swift before.mom after.mom` — only intended
   differences should be reported.
