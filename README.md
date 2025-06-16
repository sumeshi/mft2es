# mft2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/mft2es.svg)](https://badge.fury.io/py/mft2es)
[![Python Versions](https://img.shields.io/pypi/pyversions/mft2es.svg)](https://pypi.org/project/mft2es/)

![mft2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/681a72cc27829497283409e19a78808c1297c2db/mft2es.svg)

Fast import tool for Windows Master File Table (\$MFT) into Elasticsearch.

mft2es uses the Rust library [pymft-rs](https://github.com/omerbenamram/pymft-rs), making it much faster than traditional tools.

## Usage
**mft2es** can be executed from the command line or incorporated into a Python script.

```bash
$ mft2es /path/to/your/$MFT
```

or

```python
from mft2es import mft2es

if __name__ == '__main__':
  filepath = '/path/to/your/$MFT'
  mft2es(filepath)
```

### Args

mft2es supports simultaneous import of multiple files.

```bash
$ mft2es foo/MFT bar/MFT
```

Additionally, it allows for recursive import under the specified directory.

```bash
$ tree .
mftfiles/
  ├── MFT
  └── subdirectory/
    ├── MFT
    └── subsubdirectory/
      ├── MFT
      └── $MFT

$ mft2es /mftfiles/ # The path is recursively expanded to include all MFT and $MFT files.
```

### Options

```
--version, -v

--help, -h

--quiet, -q
  Flag to suppress standard output
  (default: False)

--multiprocess, -m:
  Enable multiprocessing for faster execution
  (default: False)

--size:
  Chunk size for processing (default: 500)

--host:
  ElasticSearch host address (default: localhost)

--port:
  ElasticSearch port number (default: 9200)

--index:
  Destination index name for importing (default: mft2es)

--scheme:
  Protocol scheme to use (http or https) (default: http)

--pipeline
  Elasticsearch Ingest Pipeline to use (default: )

--login:
  The login to use if Elastic Security is enabled (default: )

--pwd:
  The password associated with the provided login (default: )
```

### Examples

When using the command-line interface:

```
$ mft2es /path/to/your/$MFT --host=localhost --port=9200 --index=foobar --size=500
```

When using from a Python script:

```py
if __name__ == '__main__':
    mft2es('/path/to/your/$MFT', host=localhost, port=9200, index='foobar', size=500)
```

With credentials for Elastic Security:

```
$ mft2es /path/to/your/$MFT --host=localhost --port=9200 --index=foobar --login=elastic --pwd=******
```

Note: The current version does not verify the certificate.

## Appendix

### Mft2json

An additional feature: :sushi: :sushi: :sushi:

Convert Windows MFT to a JSON file.

```bash
$ mft2json /path/to/your/$MFT -o /path/to/output/target.json
```

Convert Windows MFT to a Python List[dict] object.

```python
from mft2es import mft2json

if __name__ == '__main__':
  filepath = '/path/to/your/$MFT'
  result: List[dict] = mft2json(filepath)
```

## Output Format

The structure is not well optimized for searching with Elasticsearch. I'm waiting for your PR!!

```json
[
  {
    "header": {
      "signature": [
        70,
        73,
        76,
        69
      ],
      "usa_offset": 48,
      "usa_size": 3,
      "metadata_transaction_journal": 172848302,
      "sequence": 1,
      "hard_link_count": 1,
      "first_attribute_record_offset": 56,
      "flags": "ALLOCATED",
      "used_entry_size": 416,
      "total_entry_size": 1024,
      "base_reference": {
        "entry": 0,
        "sequence": 0
      },
      "first_attribute_id": 6,
      "record_number": 0
    },
    "attributes": {
      "StandardInformation": {
        "header": {
          "type_code": "StandardInformation",
          "record_length": 96,
          "form_code": 0,
          "residential_header": {
            "index_flag": 0
          },
          "name_size": 0,
          "name_offset": null,
          "data_flags": "(empty)",
          "instance": 0,
          "name": ""
        },
        "data": {
          "created": "2019-03-11T16:42:33.593750Z",
          "modified": "2019-03-11T16:42:33.593750Z",
          "mft_modified": "2019-03-11T16:42:33.593750Z",
          "accessed": "2019-03-11T16:42:33.593750Z",
          "file_flags": "FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM",
          "max_version": 0,
          "version": 0,
          "class_id": 0,
          "owner_id": 0,
          "security_id": 256,
          "quota": 0,
          "usn": 0
        }
      },
      "FileName": {
        "header": {
          "type_code": "FileName",
          "record_length": 104,
          "form_code": 0,
          "residential_header": {
            "index_flag": 1
          },
          "name_size": 0,
          "name_offset": null,
          "data_flags": "(empty)",
          "instance": 3,
          "name": ""
        },
        "data": {
          "parent": {
            "entry": 5,
            "sequence": 5
          },
          "created": "2019-03-11T16:42:33.593750Z",
          "modified": "2019-03-11T16:42:33.593750Z",
          "mft_modified": "2019-03-11T16:42:33.593750Z",
          "accessed": "2019-03-11T16:42:33.593750Z",
          "logical_size": 16384,
          "physical_size": 16384,
          "flags": "FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM",
          "reparse_value": 0,
          "name_length": 4,
          "namespace": "Win32AndDos",
          "name": "$MFT",
          "path": "$MFT"
        }
      },
      "DATA": {
        "header": {
          "type_code": "DATA",
          "record_length": 72,
          "form_code": 1,
          "residential_header": {
            "vnc_first": 0,
            "vnc_last": "0x198f",
            "unit_compression_size": 0,
            "allocated_length": 62390272,
            "file_size": 62390272,
            "valid_data_length": 62390272,
            "total_allocated": null
          },
          "name_size": 0,
          "name_offset": null,
          "data_flags": "(empty)",
          "instance": 1,
          "name": ""
        },
        "data": null
      },
      "BITMAP": {
        "header": {
          "type_code": "BITMAP",
          "record_length": 80,
          "form_code": 1,
          "residential_header": {
            "vnc_first": 0,
            "vnc_last": 0,
            "unit_compression_size": 0,
            "allocated_length": 12288,
            "file_size": 8200,
            "valid_data_length": 8200,
            "total_allocated": null
          },
          "name_size": 0,
          "name_offset": null,
          "data_flags": "(empty)",
          "instance": 5,
          "name": ""
        },
        "data": null
      }
    }
  }
  ...
]
````

## Installation

### From PyPI
```
$ pip install mft2es
```

### From GitHub Releases
Pre-compiled binary versions using Nuitka are also available.

```bash
$ chmod +x ./mft2es
$ ./mft2es {{options...}}
```

```powershell
> mft2es.exe {{options...}}
```

## Contributing

The source code for mft2es is hosted on GitHub, and you can download, fork, and review it from this repository (https://github.com/sumeshi/mft2es).  
Please report issues and feature requests. :sushi: :sushi: :sushi:

## Included in
- [Tsurugi Linux [Lab] 2022 - 2024](https://tsurugi-linux.org/) - DFIR Linux distribution
Thank you for your interest in mft2es!

## License

mft2es is released under the [MIT](https://github.com/sumeshi/mft2es/blob/master/LICENSE) License.

Powered by the following libraries:
- [pymft-rs](https://github.com/omerbenamram/pymft-rs)
- [Nuitka](https://github.com/Nuitka/Nuitka)
