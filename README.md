# mft2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/mft2es)](https://pypi.org/project/mft2es/)

![mft2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/681a72cc27829497283409e19a78808c1297c2db/mft2es.svg)

A command-line tool and Python library for parsing Windows Master File Table (`$MFT`) and importing the results into Elasticsearch.

**mft2es** leverages the Rust-based parser [pymft-rs](https://github.com/omerbenamram/pymft-rs), making it faster than pure-Python parsers in many cases.


## Usage

**mft2es** can be used as a standalone command-line tool or integrated directly into your Python scripts.

```bash
$ mft2es '/path/to/your/$MFT'
```

```python
from mft2es import mft2es

mft2es("/path/to/your/$MFT")
```


### Arguments

**mft2es** can process multiple files at once:

```bash
$ mft2es 'file1/$MFT' 'file2/$MFT' 'file3/$MFT'
```

mft2es can recursively process all `MFT` and `$MFT` files under a specified directory:

```bash
$ tree .
mftfiles/
  ├── $MFT
  └── subdirectory/
    ├── $MFT
    └── subsubdirectory/
      └── $MFT

$ mft2es /mftfiles/ # The path is recursively expanded to all MFT and $MFT files.
```


### Options

```
--version, -v

--help, -h

--quiet, -q
  Suppress standard output
  (default: False)

--multiprocess, -m:
  Enable multiprocessing for faster execution
  (default: False)

--size:
  Number of records to process per chunk (default: 500)

--host:
  Elasticsearch host address (default: localhost)

--port:
  Elasticsearch port number (default: 9200)

--index:
  Destination index name (default: mft2es)

--scheme:
  Protocol scheme to use (http or https) (default: http)

--pipeline:
  Elasticsearch Ingest Pipeline to use (default: )

--timeline:
  Enable timeline analysis mode for MACB format
  (default: False)

--tags:
  Comma-separated tags to add to each record for identification
  (e.g., hostname, domain name) (default: )

--login:
  Username for Elasticsearch authentication

--pwd:
  Password for Elasticsearch authentication

--no-verify-certs:
  Disable TLS certificate verification for Elasticsearch connections (default: False)
```

### Examples

When using from the command line:

```bash
$ mft2es '/path/to/your/$MFT' --host=localhost --port=9200 --index=foobar --size=500
```

When using from a Python script:

```python
mft2es("/path/to/your/$MFT", host="localhost", port=9200, index="foobar", size=500)
```

With credentials for Elastic Security:

```bash
$ mft2es '/path/to/your/$MFT' --host=localhost --port=9200 --index=foobar --login=elastic --pwd=******
```

With timeline analysis mode:

```bash
$ mft2es '/path/to/your/$MFT' --timeline --index=mft-timeline
```

With tags for host identification:

```bash
$ mft2es '/path/to/your/$MFT' --tags "WORKSTATION-1,DOMAIN-ABC" --index=host-analysis
```

> [!WARNING]
> TLS certificate verification is enabled by default for Elasticsearch connections. Use `--no-verify-certs` only when connecting to a trusted cluster with self-signed or otherwise unverifiable certificates.


## Appendix

### mft2json

**mft2es** also includes `mft2json`, a command-line tool for converting Windows Master File Table records into JSON files. :sushi: :sushi: :sushi:

```bash
$ mft2json '/path/to/your/$MFT' -o /path/to/output/target.json
```

With tags for host identification:

```bash
$ mft2json '/path/to/your/$MFT' --tags "WORKSTATION-1,DOMAIN-ABC" -o /path/to/output/target.json
```

You can also convert `$MFT` records directly into a Python List[dict] object:

```python
from mft2es import mft2json

result: List[dict] = mft2json("/path/to/your/$MFT")
```


### Timeline Analysis

mft2es supports timeline analysis mode that creates MACB (Modified, Accessed, Changed, Birth) timeline records for forensic investigation.

```bash
$ mft2es '/path/to/your/$MFT' --timeline --index=mft-timeline
```


## Output Format Examples

### Standard Mode

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
    },
    "tags": ["mft", "WORKSTATION-1", "DOMAIN-ABC"]
  },
  ...
]
```

### Timeline Mode

```json
[
  {
    "@timestamp": "2007-06-30T12:50:52.252395Z",
    "event": {
      "action": "mft-standardinformation-m",
      "category": [
        "file"
      ],
      "type": [
        "change"
      ],
      "kind": "event",
      "provider": "mft",
      "module": "windows",
      "dataset": "windows.mft"
    },
    "windows": {
      "mft": {
        "record": {
          "number": 0,
          "name": "$MFT",
          "path": "$MFT"
        },
        "header": {
          "signature": [
            70,
            73,
            76,
            69
          ],
          "usa_offset": 48,
          "usa_size": 3,
          "metadata_transaction_journal": 77648146,
          "sequence": 1,
          "hard_link_count": 1,
          "first_attribute_record_offset": 56,
          "flags": "ALLOCATED",
          "used_entry_size": 424,
          "total_entry_size": 1024,
          "base_reference": {
            "entry": 0,
            "sequence": 0
          },
          "first_attribute_id": 6
        },
        "attribute": {
          "type": "StandardInformation",
          "macb_type": "M",
          "header": {
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
            "file_flags": "FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM",
            "max_version": 0,
            "version": 0,
            "class_id": 0,
            "owner_id": 0,
            "security_id": 256,
            "quota": 0,
            "usn": 0
          }
        }
      }
    },
    "log": {
      "file": {
        "path": "/path/to/your/MFT"
      }
    },
    "tags": [
      "mft"
    ]
  },
  ...
]
```


## Installation

### From PyPI

```bash
$ pip install mft2es
```


### With uv

```bash
$ uv add mft2es
```


### From GitHub Releases

Standalone binaries built with Nuitka are available from GitHub Releases for systems without a Python environment.

```bash
$ chmod +x ./mft2es
$ ./mft2es {{options...}}
```

```powershell
> mft2es.exe {{options...}}
```


## Contributing

The source code for **mft2es** is hosted on GitHub: https://github.com/sumeshi/mft2es.
Please report issues and feature requests. :sushi: :sushi: :sushi:


## Included in

- [Tsurugi Linux [Lab]](https://tsurugi-linux.org/) — included in selected releases.

Thank you for your interest in mft2es!

## License

Released under the [MIT](LICENSE) License.


## Third-party licenses

The standalone binaries distributed via GitHub Releases may bundle the following third-party libraries.
These libraries remain under their original licenses.

### Apache-2.0

- [elasticsearch-py / elasticsearch](https://github.com/elastic/elasticsearch-py) — licensed under the Apache License 2.0.
  - Bundled version: `elasticsearch==9.4.1`
  - License text: https://github.com/elastic/elasticsearch-py/blob/main/LICENSE

### MIT

- [mft / pymft-rs](https://github.com/omerbenamram/pymft-rs) — licensed under the MIT License.
  - Bundled version: `mft==0.6.1`
  - License text: https://github.com/omerbenamram/pymft-rs/blob/master/pyproject.toml

- [urllib3](https://github.com/urllib3/urllib3) — licensed under the MIT License.
  - Bundled version: `urllib3==2.6.3`
  - License text: https://github.com/urllib3/urllib3/blob/main/LICENSE.txt

### Apache-2.0 OR MIT, with MPL-2.0 components

- [orjson](https://github.com/ijl/orjson) — licensed under Apache-2.0 OR MIT, and contains source code licensed under MPL-2.0.
  - Bundled version: `orjson==3.11.9`
  - License text:
    - https://github.com/ijl/orjson/blob/master/LICENSE-APACHE
    - https://github.com/ijl/orjson/blob/master/LICENSE-MIT
    - https://github.com/ijl/orjson/blob/master/LICENSE-MPL-2.0

### MIT and MPL-2.0

- [tqdm](https://github.com/tqdm/tqdm) — licensed under MIT, with MPL-2.0-covered files/components.
  - Bundled version: `tqdm==4.67.3`
  - License text: https://github.com/tqdm/tqdm/blob/master/LICENCE
