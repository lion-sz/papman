# Data Model

The data model is quite simple.

There is one root library path.
In this path I 2 or more files for each entry:

- {id}.xml: A xml file written by me that contains some general information, as well as links to the pdf files.
- {id}.json: The json source file that contains all information I get from DOI.
  Dumped almost as received.
- Potential attachments, linked in the .xml file.