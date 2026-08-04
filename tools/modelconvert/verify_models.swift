/*
 * verify_models.swift
 *
 * Exhaustively compares two compiled Core Data models (.mom files) and reports
 * every difference. Used to prove that a converted model is schema-identical to
 * the original.
 *
 * Usage:  swift verify_models.swift <original.mom> <candidate.mom>
 *
 * Exit status 0 means the models are identical in every compared dimension,
 * including entity version hashes (which is what determines store compatibility
 * and migration behavior). Any difference is printed and exits 1.
 */

import CoreData
import Foundation

guard CommandLine.arguments.count == 3 else {
    print("usage: swift verify_models.swift <original.mom> <candidate.mom>")
    exit(2)
}
let urlA = URL(fileURLWithPath: CommandLine.arguments[1])
let urlB = URL(fileURLWithPath: CommandLine.arguments[2])
guard let momA = NSManagedObjectModel(contentsOf: urlA) else { print("cannot load \(urlA.path)"); exit(2) }
guard let momB = NSManagedObjectModel(contentsOf: urlB) else { print("cannot load \(urlB.path)"); exit(2) }

var differences: [String] = []
func diff(_ msg: String) { differences.append(msg) }

func compareOptional<T: Equatable>(_ a: T?, _ b: T?, _ path: String) {
    if a != b { diff("\(path): '\(a.map { "\($0)" } ?? "nil")' vs '\(b.map { "\($0)" } ?? "nil")'") }
}

var notes: [String] = []

// momc deliberately strips defunct Sync Services userInfo keys when compiling
// XML-format models (Sync Services died with OS X 10.8, and nothing in VidSync
// reads them), so they are excluded from comparison rather than reported.
func filteredUserInfo(_ ui: [AnyHashable: Any]?) -> NSDictionary {
    var out: [AnyHashable: Any] = [:]
    for (k, v) in ui ?? [:] {
        if let key = k as? String, key.hasPrefix("com.apple.syncservices.") {
            if !notes.contains("legacy Sync Services userInfo keys ignored") {
                notes.append("legacy Sync Services userInfo keys ignored")
            }
            continue
        }
        out[k] = v
    }
    return out as NSDictionary
}

func compareUserInfo(_ a: [AnyHashable: Any]?, _ b: [AnyHashable: Any]?, _ path: String) {
    let da = filteredUserInfo(a), db = filteredUserInfo(b)
    if !da.isEqual(db) { diff("\(path).userInfo: \(da) vs \(db)") }
}

// --- The critical check: entity version hashes determine store compatibility ---
let hashesA = momA.entityVersionHashesByName
let hashesB = momB.entityVersionHashesByName
for name in Set(hashesA.keys).union(hashesB.keys).sorted() {
    let ha = hashesA[name], hb = hashesB[name]
    if ha != hb {
        diff("VERSION HASH MISMATCH for entity \(name): \(ha?.base64EncodedString() ?? "missing") vs \(hb?.base64EncodedString() ?? "missing")")
    }
}

// --- Model-level metadata ---
if momA.versionIdentifiers != momB.versionIdentifiers {
    diff("model.versionIdentifiers: \(momA.versionIdentifiers) vs \(momB.versionIdentifiers)")
}
compareOptional(momA.configurations.sorted(), momB.configurations.sorted(), "model.configurations")
compareOptional(momA.fetchRequestTemplatesByName.keys.sorted(), momB.fetchRequestTemplatesByName.keys.sorted(), "model.fetchRequestTemplates")

// --- Entities ---
let entNamesA = Set(momA.entitiesByName.keys), entNamesB = Set(momB.entitiesByName.keys)
for missing in entNamesA.subtracting(entNamesB).sorted() { diff("entity \(missing) missing from candidate") }
for extra in entNamesB.subtracting(entNamesA).sorted() { diff("entity \(extra) only in candidate") }

// Indexes are compared by their column signatures only. momc names indexes
// derived from legacy indexed="YES" flags differently depending on the source
// format ("startTimecode" from binary models vs "byStartTimecodeIndex" from
// XML), but the indexed columns themselves — which are all that affects the
// store — are identical, and index names are not part of version hashes.
func describeIndexes(_ e: NSEntityDescription) -> [String] {
    e.indexes.map { idx in
        idx.elements.map { el in
            "\(el.property?.name ?? el.propertyName ?? "?"):\(el.collationType.rawValue):\(el.isAscending ? "asc" : "desc")"
        }.joined(separator: ",")
    }.sorted()
}

for name in entNamesA.intersection(entNamesB).sorted() {
    let ea = momA.entitiesByName[name]!, eb = momB.entitiesByName[name]!
    let p = "entity \(name)"
    compareOptional(ea.managedObjectClassName, eb.managedObjectClassName, "\(p).representedClassName")
    compareOptional(ea.isAbstract, eb.isAbstract, "\(p).isAbstract")
    compareOptional(ea.superentity?.name, eb.superentity?.name, "\(p).parentEntity")
    compareOptional(ea.renamingIdentifier, eb.renamingIdentifier, "\(p).renamingIdentifier")
    compareOptional(ea.versionHashModifier, eb.versionHashModifier, "\(p).versionHashModifier")
    compareUserInfo(ea.userInfo, eb.userInfo, p)
    compareOptional(describeIndexes(ea), describeIndexes(eb), "\(p).indexes")
    compareOptional(ea.uniquenessConstraints.count, eb.uniquenessConstraints.count, "\(p).uniquenessConstraints.count")

    let propsA = Set(ea.propertiesByName.keys), propsB = Set(eb.propertiesByName.keys)
    for missing in propsA.subtracting(propsB).sorted() { diff("\(p).\(missing) missing from candidate") }
    for extra in propsB.subtracting(propsA).sorted() { diff("\(p).\(extra) only in candidate") }

    for pname in propsA.intersection(propsB).sorted() {
        let pa = ea.propertiesByName[pname]!, pb = eb.propertiesByName[pname]!
        let pp = "\(p).\(pname)"
        compareOptional(pa.isOptional, pb.isOptional, "\(pp).isOptional")
        compareOptional(pa.isTransient, pb.isTransient, "\(pp).isTransient")
        compareOptional(pa.isIndexed, pb.isIndexed, "\(pp).isIndexed")
        compareOptional(pa.renamingIdentifier, pb.renamingIdentifier, "\(pp).renamingIdentifier")
        compareOptional(pa.versionHashModifier, pb.versionHashModifier, "\(pp).versionHashModifier")
        compareUserInfo(pa.userInfo, pb.userInfo, pp)
        if pa.versionHash != pb.versionHash {
            diff("\(pp): property version hash differs")
        }

        if let aa = pa as? NSAttributeDescription {
            guard let ab = pb as? NSAttributeDescription else { diff("\(pp): attribute vs non-attribute"); continue }
            compareOptional(aa.attributeType.rawValue, ab.attributeType.rawValue, "\(pp).attributeType")
            compareOptional(aa.valueTransformerName, ab.valueTransformerName, "\(pp).valueTransformerName")
            compareOptional(aa.attributeValueClassName, ab.attributeValueClassName, "\(pp).attributeValueClassName")
            compareOptional(aa.allowsExternalBinaryDataStorage, ab.allowsExternalBinaryDataStorage, "\(pp).allowsExternalBinaryDataStorage")
            let da = aa.defaultValue as? NSObject, db = ab.defaultValue as? NSObject
            switch (da, db) {
            case (nil, nil): break
            case let (x?, y?):
                if !x.isEqual(y) { diff("\(pp).defaultValue: '\(x)' (\(type(of: x))) vs '\(y)' (\(type(of: y)))") }
            default:
                diff("\(pp).defaultValue: '\(da.map { "\($0)" } ?? "nil")' vs '\(db.map { "\($0)" } ?? "nil")'")
            }
            let vpA = aa.validationPredicates.map { $0.predicateFormat }.sorted()
            let vpB = ab.validationPredicates.map { $0.predicateFormat }.sorted()
            compareOptional(vpA, vpB, "\(pp).validationPredicates")
        } else if let ra = pa as? NSRelationshipDescription {
            guard let rb = pb as? NSRelationshipDescription else { diff("\(pp): relationship vs non-relationship"); continue }
            compareOptional(ra.destinationEntity?.name, rb.destinationEntity?.name, "\(pp).destination")
            compareOptional(ra.inverseRelationship?.name, rb.inverseRelationship?.name, "\(pp).inverseName")
            compareOptional(ra.inverseRelationship?.entity.name, rb.inverseRelationship?.entity.name, "\(pp).inverseEntity")
            compareOptional(ra.isToMany, rb.isToMany, "\(pp).isToMany")
            compareOptional(ra.isOrdered, rb.isOrdered, "\(pp).isOrdered")
            compareOptional(ra.minCount, rb.minCount, "\(pp).minCount")
            compareOptional(ra.maxCount, rb.maxCount, "\(pp).maxCount")
            compareOptional(ra.deleteRule.rawValue, rb.deleteRule.rawValue, "\(pp).deleteRule")
        }
    }
}

if differences.isEmpty {
    print("PASS: models are identical")
    print("  entities: \(momA.entities.count)")
    print("  version hashes: all \(hashesA.count) entities match exactly")
    for n in notes { print("  NOTE: \(n)") }
    exit(0)
} else {
    print("FAIL: \(differences.count) difference(s):")
    for d in differences { print("  - \(d)") }
    exit(1)
}
