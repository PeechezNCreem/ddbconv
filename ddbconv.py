#!/usr/bin/env python3

#                 Copyright 2021 PeechezNCreem
#  Distributed under the Boost Software License, Version 1.0.
#          (See accompanying file LICENSE or copy at
#            https://www.boost.org/LICENSE_1_0.txt)

import enum
import pathlib
import struct


class Stream:
    def __init__(self, filepath, offset=0):
        self.raw = pathlib.Path(filepath).read_bytes()
        self.length = len(self.raw)
        self.offset = offset

    def empty(self):
        return self.offset >= self.length

    def read(self, fmt):
        offset = self.offset + struct.calcsize(fmt)
        value = struct.unpack(fmt, self.raw[self.offset:offset])
        self.offset = offset
        return value if len(value) != 1 else value[0]


class Field:
    def __init__(self, name, value_type, value, attributes):
        self.name = name
        self.value_type = value_type
        self.value = value
        self.attributes = attributes

    def __bytes__(self):
        if self.value == "" and self.value_type not in (Type.STR, Type.WSTR):
            self.value = 0
        return type_writer_map[self.value_type](self.value)[0]

    def __str__(self):
        attribs = ["=".join((k, f'"{v}"')) for k, v in self.attributes.items()]
        return f"<{self.name} {' '.join(attribs)}>{self.value}</{self.name}>"

    def template(self):
        return (
            type_writer_map[Type.STR](self.name)[0]
            + struct.pack("B", self.value_type.value)
            + b"\x28"
        )


Type = enum.IntEnum("Type", "GID INT UINT FLT BYT UBYT USHRT DBL STR WSTR")

type_reader_map = {
    Type.GID:   lambda s: (s.read("Q"), 8),
    Type.INT:   lambda s: (s.read("i"), 4),
    Type.UINT:  lambda s: (s.read("I"), 4),
    Type.FLT:   lambda s: (s.read("f"), 4),
    Type.BYT:   lambda s: (s.read("b"), 1),
    Type.UBYT:  lambda s: (s.read("B"), 1),
    Type.USHRT: lambda s: (s.read("H"), 2),
    Type.DBL:   lambda s: (s.read("d"), 8),
    Type.STR:   lambda s: (s.read(f"{(l := s.read('H'))}s").decode(), 2 + l),
    Type.WSTR:  lambda s: (
        s.read(f"{(l := 2 * s.read('H'))}s").decode(encoding="utf-16-le"),
        2 + l,
    ),
}

type_writer_map = {
    Type.GID:   lambda v: (struct.pack("Q", int(v)), 8),
    Type.INT:   lambda v: (struct.pack("i", int(v)), 4),
    Type.UINT:  lambda v: (struct.pack("I", int(v)), 4),
    Type.FLT:   lambda v: (struct.pack("f", float(v)), 4),
    Type.BYT:   lambda v: (struct.pack("b", int(v)), 1),
    Type.UBYT:  lambda v: (struct.pack("B", int(v)), 1),
    Type.USHRT: lambda v: (struct.pack("H", int(v)), 2),
    Type.DBL:   lambda v: (struct.pack("d", float(d)), 8),
    Type.STR:   lambda v: (
        struct.pack(f"H{(l := len(v))}s", l, v.encode()),
        2 + l,
    ),
    Type.WSTR:  lambda v: (
        struct.pack(f"H{(l := 2 * len(v))}s", l, v.encode("utf-16-le")),
        2 + l,
    ),
}


def _deserialize_record_template(stream):
    template, size = [], stream.read("H") - 4
    target = None
    while size > 0:
        length = stream.read("H")
        size -= 2
        name = stream.read(f"{length}s").decode()
        size -= length

        typ, _ = stream.read("BB")
        size -= 2
        assert typ in type_reader_map

        if name == "_TargetTable":
            length = stream.read("H")
            size -= 2
            target = stream.read(f"{length}s").decode()
            size -= length
            continue

        template.append((name, Type(typ)))
    assert target is not None
    return template, target


def _deserialize_record(stream, template):
    """ Deserialize a DML record (list of fields) """
    record = []

    size = stream.read("H")
    for name, typ in template:
        assert size > 0
        attributes = {"TYPE": typ.name}

        # add basic (unofficial) support for message modules
        if name.startswith("_"):
            attributes["NOXFER"] = "TRUE"

        value, n = type_reader_map[typ](stream)
        size -= n
        record.append(Field(name, typ, value, attributes))
    return record


def _deserialize_table(stream):
    """ Deserialize a DML table (list of records) """
    table, record_count = [], stream.read("I")
    for _ in range(record_count + 1):
        _, srv = stream.read("BB")
        if srv == 1:
            record_template, target = _deserialize_record_template(stream)
        elif srv == 2:
            assert record_template is not None
            assert target is not None
            table.append(_deserialize_record(stream, record_template))
    assert len(table) == record_count
    assert target is not None
    return table, target


def deserialize(filepath):
    """ Load DML tables from binary """
    stream, tables = Stream(filepath), {}
    while not stream.empty():
        table, target = _deserialize_table(stream)
        tables[target] = table
    return tables


def load(filepath):
    """ Load DML tables from XML """
    from xml.etree import ElementTree

    root, tables = ElementTree.parse(filepath).getroot(), {}
    for table in root:
        records = []
        for record in table:
            fields = []
            for field in record:
                if field.text is None:
                    field.text = ""
                try:
                    fields.append(
                        Field(
                            field.tag,
                            Type[field.attrib["TYPE"]],
                            field.text,
                            field.attrib,
                        )
                    )
                except KeyError:
                    raise KeyError(field.tag, field.attrib.keys())
            records.append(fields)
        tables[table.tag] = records
    return tables


def serialize(tables, filepath):
    """ Save tables to binary """
    data = []
    for table, records in tables.items():
        data.append(struct.pack("I", len(records)))

        template_data = (
            b"".join(f.template() for f in records[0])
            + b"\x0C\x00_TargetTable\x09\x28"
            + struct.pack("H", len(table))
            + table.encode()
        )
        data.append(
            b"\x02\x01" + struct.pack("H", len(template_data) + 4) + template_data
        )

        for record in records:
            record_data = b"".join(bytes(f) for f in record)
            data.append(
                b"\x02\x02" + struct.pack("H", len(record_data) + 4) + record_data
            )
    filepath.write_bytes(b"".join(data))


def save(tables, filepath):
    """ Save tables to XML """
    lines = ['<?xml version="1.0" encoding="utf-8"?>']
    lines.append(f"<{filepath.stem}>")
    for table, records in tables.items():
        lines.append(f"  <{table}>")
        for record in records:
            lines.append(f"    <RECORD>")
            for field in record:
                lines.append(f"      {str(field)}")
            lines.append(f"    </RECORD>")
        lines.append(f"  </{table}>")
    lines.append(f"</{filepath.stem}>")
    lines.append("")
    filepath.write_text("\n".join(lines))


if __name__ == "__main__":
    import sys

    try:
        filepath = sys.argv[1]
    except IndexError:
        from tkinter import Tk
        from tkinter.filedialog import askopenfilename

        (root := Tk()).withdraw()
        filepath = askopenfilename(
            parent=root,
            title="Select DML database to load",
            initialdir=".",
            filetypes=[
                ("Binary files", "*.bin"),
                ("XML file", "*.xml"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        if not filepath:
            sys.exit()

    filepath = pathlib.Path(filepath)
    if filepath.suffix == ".xml":
        serialize(load(filepath), filepath.with_suffix(".bin"))
    else:
        save(deserialize(filepath), filepath.with_suffix(".xml"))
