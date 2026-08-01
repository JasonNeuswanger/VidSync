#!/usr/bin/env python3
"""Check that a VidSync JSON export says exactly what its XML twin says.

The JSON export is produced by mechanically transforming the same NSXMLDocument the XML export
writes, so the two should never disagree. This checks that they don't, which is the only thing
standing between the hand-maintained attribute type table in DataExport.m and a silent mistake.

    python3 tools/export_parity.py "some project.xml" "some project.json"

Both files must come from the same export run of the same project. Exits nonzero and prints every
difference it finds if they disagree.

The rules the converter follows, restated here so this check is independent of it:

  * An element becomes an object; the document is {"project": {...}}.
  * Attributes become keys.
  * Child elements are grouped by tag name into arrays, always arrays, in document order.
  * An element with text and no child elements puts its text under "text".
  * An empty attribute becomes null; YES/NO become true/false; a {{...}} matrix becomes a nested
    list of numbers; the rest are numbers or strings.
"""

import json
import re
import sys
import xml.etree.ElementTree as etree

problems = []


def note(path, message):
    problems.append(f"{path}: {message}")


def matches_matrix(xml_value, json_value, path, key):
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", xml_value)]
    if len(numbers) != 9:
        if json_value is not None:
            note(path, f"{key}: XML {xml_value!r} is not nine numbers but JSON has {json_value!r}")
        return
    flat = [v for row in json_value for v in row]
    if len(json_value) != 3 or any(len(row) != 3 for row in json_value):
        note(path, f"{key}: JSON matrix is not 3x3: {json_value!r}")
    elif any(a != b for a, b in zip(numbers, flat)):
        note(path, f"{key}: matrix values differ, XML {numbers} vs JSON {flat}")


def check_value(path, key, xml_value, json_value):
    if json_value is None:
        if xml_value != "":
            note(path, f"{key}: JSON is null but XML is {xml_value!r}")
    elif isinstance(json_value, bool):
        if xml_value not in ("YES", "NO"):
            note(path, f"{key}: JSON is a boolean but XML is {xml_value!r}")
        elif json_value != (xml_value == "YES"):
            note(path, f"{key}: JSON {json_value} vs XML {xml_value!r}")
    elif isinstance(json_value, (int, float)):
        try:
            if float(xml_value) != json_value:
                note(path, f"{key}: JSON {json_value!r} vs XML {xml_value!r}")
        except ValueError:
            note(path, f"{key}: JSON is a number but XML {xml_value!r} is not")
    elif isinstance(json_value, list):
        matches_matrix(xml_value, json_value, path, key)
    elif isinstance(json_value, str):
        if json_value != xml_value:
            note(path, f"{key}: JSON {json_value!r} vs XML {xml_value!r}")
    else:
        note(path, f"{key}: unexpected JSON value {json_value!r}")


def check_element(element, obj, path):
    if not isinstance(obj, dict):
        note(path, f"expected a JSON object, found {type(obj).__name__}")
        return

    for key, xml_value in element.attrib.items():
        if key not in obj:
            note(path, f"attribute {key!r} is missing from the JSON")
        else:
            check_value(path, key, xml_value, obj[key])

    children_by_tag = {}
    for child in element:
        children_by_tag.setdefault(child.tag, []).append(child)

    text = (element.text or "").strip()
    expected_keys = set(element.attrib) | set(children_by_tag)
    if not children_by_tag and text:
        expected_keys.add("text")
        if obj.get("text", "").strip() != text:
            note(path, f"text differs: JSON {obj.get('text')!r} vs XML {element.text!r}")

    for key in set(obj) - expected_keys:
        note(path, f"the JSON has {key!r}, which is not in the XML")

    for tag, children in children_by_tag.items():
        group = obj.get(tag)
        if not isinstance(group, list):
            note(path, f"<{tag}> children should be a JSON array, found {type(group).__name__}")
            continue
        if len(group) != len(children):
            note(path, f"<{tag}>: {len(children)} in the XML, {len(group)} in the JSON")
            continue
        for i, (child, child_obj) in enumerate(zip(children, group)):
            check_element(child, child_obj, f"{path}/{tag}[{i}]")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    root = etree.parse(sys.argv[1]).getroot()
    document = json.load(open(sys.argv[2]))

    if list(document) != [root.tag]:
        print(f"The JSON root should be a single {root.tag!r} key, found {list(document)}")
        return 1
    check_element(root, document[root.tag], root.tag)

    if problems:
        print(f"{len(problems)} difference(s) between the two exports:")
        for problem in problems:
            print("  " + problem)
        return 1
    print("The JSON and the XML carry the same content.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
