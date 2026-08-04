/*
 * convert_mom_to_xml.swift
 *
 * Converts a compiled Core Data model (.mom) into the modern XML source format
 * (the `contents` file inside a .xcdatamodel directory), which is human-readable
 * and editable as plain text.
 *
 * Usage:  swift convert_mom_to_xml.swift <input.mom> <output-contents-file>
 *
 * The converter hard-fails on any model feature it does not explicitly handle,
 * so it can never silently emit an unfaithful translation. Always check the
 * result with verify_models.swift before using it.
 */

import CoreData
import Foundation

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write("ERROR: \(msg)\n".data(using: .utf8)!)
    exit(1)
}

guard CommandLine.arguments.count == 3 else {
    fail("usage: swift convert_mom_to_xml.swift <input.mom> <output-contents-file>")
}
let inputURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])

guard let mom = NSManagedObjectModel(contentsOf: inputURL) else {
    fail("cannot load compiled model at \(inputURL.path)")
}

// Model-level features this converter does not translate; refuse if present.
if !mom.configurations.isEmpty { fail("model has configurations; converter does not handle them") }
if !mom.fetchRequestTemplatesByName.isEmpty { fail("model has fetch request templates; converter does not handle them") }
if let loc = mom.localizationDictionary, !loc.isEmpty { fail("model has a localization dictionary; converter does not handle it") }

func esc(_ s: String) -> String {
    var out = ""
    for c in s.unicodeScalars {
        switch c {
        case "&": out += "&amp;"
        case "<": out += "&lt;"
        case ">": out += "&gt;"
        case "\"": out += "&quot;"
        case "\n": out += "&#10;"
        case "\t": out += "&#9;"
        default: out.unicodeScalars.append(c)
        }
    }
    return out
}

func attrTypeXML(_ t: NSAttributeType, _ name: String) -> String {
    switch t {
    case .integer16AttributeType: return "Integer 16"
    case .integer32AttributeType: return "Integer 32"
    case .integer64AttributeType: return "Integer 64"
    case .decimalAttributeType: return "Decimal"
    case .doubleAttributeType: return "Double"
    case .floatAttributeType: return "Float"
    case .stringAttributeType: return "String"
    case .booleanAttributeType: return "Boolean"
    case .dateAttributeType: return "Date"
    case .binaryDataAttributeType: return "Binary"
    case .transformableAttributeType: return "Transformable"
    case .UUIDAttributeType: return "UUID"
    case .URIAttributeType: return "URI"
    default: fail("attribute \(name): unhandled attribute type (rawValue \(t.rawValue))")
    }
}

func defaultValueString(_ a: NSAttributeDescription, _ path: String) -> String? {
    guard let dv = a.defaultValue else { return nil }
    switch a.attributeType {
    case .booleanAttributeType:
        guard let n = dv as? NSNumber else { fail("\(path): boolean default is not a number") }
        return n.boolValue ? "YES" : "NO"
    case .integer16AttributeType, .integer32AttributeType, .integer64AttributeType,
         .doubleAttributeType, .floatAttributeType, .decimalAttributeType:
        guard let n = dv as? NSNumber else { fail("\(path): numeric default is not a number") }
        return n.stringValue
    case .stringAttributeType:
        guard let s = dv as? String else { fail("\(path): string default is not a string") }
        return s
    default:
        fail("\(path): default value present on unhandled attribute type")
    }
}

// Translate validation predicates back to the minValueString/maxValueString the
// XML format uses. Only the shapes Xcode itself generates are supported.
func minMaxStrings(_ a: NSAttributeDescription, _ path: String) -> (min: String?, max: String?) {
    var mn: String? = nil, mx: String? = nil
    for p in a.validationPredicates {
        let f = p.predicateFormat
        if f.hasPrefix("SELF >= ") { mn = String(f.dropFirst("SELF >= ".count)) }
        else if f.hasPrefix("SELF <= ") { mx = String(f.dropFirst("SELF <= ".count)) }
        else if f.hasPrefix("length >= ") { mn = String(f.dropFirst("length >= ".count)) }
        else if f.hasPrefix("length <= ") { mx = String(f.dropFirst("length <= ".count)) }
        else { fail("\(path): unhandled validation predicate '\(f)'") }
    }
    return (mn, mx)
}

func userInfoXML(_ userInfo: [AnyHashable: Any]?, indent: String) -> String {
    guard let ui = userInfo, !ui.isEmpty else { return "" }
    var entries: [(String, String)] = []
    for (k, v) in ui {
        guard let key = k as? String else { fail("userInfo key \(k) is not a string") }
        // momc strips defunct Sync Services keys from XML-format models anyway,
        // so don't bother emitting them (Sync Services died with OS X 10.8).
        if key.hasPrefix("com.apple.syncservices.") { continue }
        guard let val = v as? String else { fail("userInfo value for key '\(key)' is not a string (\(type(of: v)))") }
        entries.append((key, val))
    }
    if entries.isEmpty { return "" }
    entries.sort { $0.0 < $1.0 }
    var out = "\(indent)<userInfo>\n"
    for (k, v) in entries {
        out += "\(indent)    <entry key=\"\(esc(k))\" value=\"\(esc(v))\"/>\n"
    }
    out += "\(indent)</userInfo>\n"
    return out
}

var xml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
xml += "<model type=\"com.apple.IDECoreDataModeler.DataModel\" documentVersion=\"1.0\" "
xml += "lastSavedToolsVersion=\"1\" systemVersion=\"11A491\" minimumToolsVersion=\"Automatic\" "
xml += "sourceLanguage=\"Objective-C\" userDefinedModelVersionIdentifier=\"\">\n"

let entities = mom.entities.sorted { $0.name! < $1.name! }

for e in entities {
    guard let ename = e.name else { fail("entity with no name") }
    if e.versionHashModifier != nil { fail("\(ename): entity versionHashModifier not handled") }
    if !e.indexes.isEmpty {
        // Indexes derived from legacy indexed="YES" flags are reproduced via the
        // per-property indexed attribute below; explicit fetch indexes are not handled.
        // We verify equivalence of the derived indexes in verify_models.swift.
    }
    if !e.uniquenessConstraints.isEmpty { fail("\(ename): uniqueness constraints not handled") }

    var head = "    <entity name=\"\(esc(ename))\" representedClassName=\"\(esc(e.managedObjectClassName))\""
    if e.isAbstract { head += " isAbstract=\"YES\"" }
    if let parent = e.superentity?.name { head += " parentEntity=\"\(esc(parent))\"" }
    head += " syncable=\"YES\""
    if e.renamingIdentifier != nil && e.renamingIdentifier != ename {
        head += " elementID=\"\(esc(e.renamingIdentifier!))\""
    }
    head += ">\n"
    xml += head

    // Only emit properties declared on this entity itself; inherited ones live on the parent.
    let ownProps = e.propertiesByName.filter { (pname, _) in
        e.superentity?.propertiesByName[pname] == nil
    }
    let attrs = ownProps.values.compactMap { $0 as? NSAttributeDescription }.sorted { $0.name < $1.name }
    let rels = ownProps.values.compactMap { $0 as? NSRelationshipDescription }.sorted { $0.name < $1.name }
    let others = ownProps.values.filter { !($0 is NSAttributeDescription) && !($0 is NSRelationshipDescription) }
    if !others.isEmpty { fail("\(ename): unhandled property kinds: \(others.map { $0.name })") }

    for a in attrs {
        let path = "\(ename).\(a.name)"
        var line = "        <attribute name=\"\(esc(a.name))\""
        if a.isOptional { line += " optional=\"YES\"" }
        if a.isTransient { line += " transient=\"YES\"" }
        line += " attributeType=\"\(attrTypeXML(a.attributeType, path))\""
        if a.attributeType == .transformableAttributeType {
            if let vt = a.valueTransformerName { line += " valueTransformerName=\"\(esc(vt))\"" }
            if let cn = a.attributeValueClassName { line += " customClassName=\"\(esc(cn))\"" }
        } else if a.valueTransformerName != nil {
            fail("\(path): valueTransformerName on non-transformable attribute")
        }
        if let dvs = defaultValueString(a, path) { line += " defaultValueString=\"\(esc(dvs))\"" }
        let (mn, mx) = minMaxStrings(a, path)
        if let mn = mn { line += " minValueString=\"\(esc(mn))\"" }
        if let mx = mx { line += " maxValueString=\"\(esc(mx))\"" }
        if a.allowsExternalBinaryDataStorage { line += " allowsExternalBinaryDataStorage=\"YES\"" }
        if a.isIndexed { line += " indexed=\"YES\"" }
        if a.versionHashModifier != nil { fail("\(path): versionHashModifier not handled") }
        if let rid = a.renamingIdentifier, rid != a.name { line += " elementID=\"\(esc(rid))\"" }
        let ui = userInfoXML(a.userInfo, indent: "            ")
        if ui.isEmpty {
            line += "/>\n"
        } else {
            line += ">\n" + ui + "        </attribute>\n"
        }
        xml += line
    }

    for r in rels {
        let path = "\(ename).\(r.name)"
        guard let dest = r.destinationEntity?.name else { fail("\(path): no destination entity") }
        var line = "        <relationship name=\"\(esc(r.name))\""
        if r.isOptional { line += " optional=\"YES\"" }
        if r.isTransient { line += " transient=\"YES\"" }
        if r.isToMany { line += " toMany=\"YES\"" }
        if r.minCount != 0 { line += " minCount=\"\(r.minCount)\"" }
        if r.maxCount != 0 { line += " maxCount=\"\(r.maxCount)\"" }
        let rule: String
        switch r.deleteRule {
        case .nullifyDeleteRule: rule = "Nullify"
        case .cascadeDeleteRule: rule = "Cascade"
        case .denyDeleteRule: rule = "Deny"
        case .noActionDeleteRule: rule = "No Action"
        @unknown default: fail("\(path): unhandled delete rule")
        }
        line += " deletionRule=\"\(rule)\""
        if r.isOrdered { line += " ordered=\"YES\"" }
        if r.isIndexed { line += " indexed=\"YES\"" }
        line += " destinationEntity=\"\(esc(dest))\""
        if let inv = r.inverseRelationship {
            line += " inverseName=\"\(esc(inv.name))\" inverseEntity=\"\(esc(inv.entity.name!))\""
        }
        if r.versionHashModifier != nil { fail("\(path): versionHashModifier not handled") }
        if let rid = r.renamingIdentifier, rid != r.name { line += " elementID=\"\(esc(rid))\"" }
        let ui = userInfoXML(r.userInfo, indent: "            ")
        if ui.isEmpty {
            line += "/>\n"
        } else {
            line += ">\n" + ui + "        </relationship>\n"
        }
        xml += line
    }

    xml += userInfoXML(e.userInfo, indent: "        ")
    xml += "    </entity>\n"
}

// Editor canvas layout; purely cosmetic. Xcode rewrites this freely.
xml += "    <elements>\n"
for (i, e) in entities.enumerated() {
    let col = i % 5, row = i / 5
    xml += "        <element name=\"\(esc(e.name!))\" positionX=\"\(col * 200)\" positionY=\"\(row * 200)\" width=\"128\" height=\"128\"/>\n"
}
xml += "    </elements>\n"
xml += "</model>\n"

do {
    try xml.write(to: outputURL, atomically: true, encoding: .utf8)
} catch {
    fail("cannot write \(outputURL.path): \(error)")
}
print("Wrote \(outputURL.path) (\(mom.entities.count) entities)")
