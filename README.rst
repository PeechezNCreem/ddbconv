ddbconv
=======

Simple DML table serialization and deserialization for KingsIsle games. Common usage is parsing ``LatestFileList.bin`` for Wizard101 and Pirate101.

Utility Usage
=============
Using ``ddbconv`` as a utility requires a Python interpreter to execute it. If you don't pass a file path argument to it you will be prompted to select a file.

``usage: ddbconv [file]``

Library Usage
=============
``ddbconv`` can be used in Python by importing the module and using the public API:

* ``deserialize(filepath)``: Load DML tables from a binary file.
* ``load(filepath)``: Load DML tables from an XML file.
* ``serialize(tables, filepath)``: Save tables to a binary file.
* ``save(tables, filepath)``: Save tables to an XML file.

See bottom of ``ddbconv.py`` for example usage.
