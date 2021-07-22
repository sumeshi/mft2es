# mft2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/mft2es.svg)](https://badge.fury.io/py/mft2es)
[![Python Versions](https://img.shields.io/pypi/pyversions/mft2es.svg)](https://pypi.org/project/mft2es/)
[![DockerHub Status](https://shields.io/docker/cloud/build/sumeshi/mft2es)](https://hub.docker.com/r/sumeshi/mft2es)

![mft2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/681a72cc27829497283409e19a78808c1297c2db/mft2es.svg)

Fast import of Windows Master File Table(\$MFT) into Elasticsearch.

mft2es uses Rust library [pymft-rs](https://github.com/omerbenamram/pymft-rs).

## Usage

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

mft2es supports multiple file input, all arguments are determined as file paths.

```bash
$ mft2es foo/MFT bar/MFT
```

or

```bash
$ tree .
mftfiles/
  ├── MFT
  └── subdirectory/
    ├── MFT
    └── subsubdirectory/
      ├── MFT
      └── $MFT

$ mft2es /mftfiles/ # The Path is recursively expanded to all MFT, and $MFT.
```

### Options

```
--version, -v

--help, -h

--quiet, -q
  Flag to suppress standard output
  (default: False)

--multiprocess, -m:
  Flag to run multiprocessing (fast!)
  (default: False)

--size:
  Size of the chunk to be processed for each process
  (default: 500)

--host:
  ElasticSearch host address
  (default: localhost)

--port:
  ElasticSearch port number
  (default: 9200)

--index:
  Index name
  (default: mft2es)

--scheme:
  Scheme to use (http, or https)
  (default: http)

--pipeline
  Elasticsearch Ingest Pipeline to use
  (default: )

--login:
  The login to use if Elastic Security is enable
  (default: )

--pwd:
  The password linked to the login provided
  (default: )
```

### Examples

When using from the commandline interface:

```
$ mft2es /path/to/your/$MFT --host=localhost --port=9200 --index=foobar --size=500
```

When using from the python-script:

```py
if __name__ == '__main__':
    mft2es('/path/to/your/$MFT', host=localhost, port=9200, index='foobar', size=500)
```

With the Amazon Elasticsearch Serivce (ES):

```
$ mft2es /path/to/your/$MFT --host=example.us-east-1.es.amazonaws.com --port=443 --scheme=https --index=foobar
```

With credentials for Elastic Security:

```
$ mft2es /path/to/your/$MFT --host=localhost --port=9200 --index=foobar --login=elastic --pwd=******
```

Note: The current version does not verify the certificate.

## Appendix

### Mft2json

Extra feature. :sushi: :sushi: :sushi:

Convert from Windows MFT to json file.

```bash
$ mft2json /path/to/your/$MFT -o /path/to/output/target.json
```

or

```python
from mft2json import mft2json

if __name__ == '__main__':
  filepath = '/path/to/your/$MFT'
  result: List[dict] = mft2json(filepath)
```


## Output Format

The structures is not well optimized for searchable with Elasticsearch. I'm waiting for your PR!!

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

### via PyPI
```
$ pip install mft2es
```

### via DockerHub
```
$ docker pull sumeshi/mft2es:latest
```

## Run with Docker
https://hub.docker.com/r/sumeshi/mft2es


## mft2es
```bash
# "host.docker.internal" is only available in mac and windows environments.
# For linux, use the --add-host option.
$ docker run -t --rm -v $(pwd):/app/work sumeshi/mft2es:latest mft2es /app/work/\$MFT --host=host.docker.internal
```

## mft2json
```bash
$ docker run -t --rm -v $(pwd):/app/work sumeshi/mft2es:latest mft2json /app/work/\$MFT /app/work/out.json
```

Do not use the "latest" image if at all possible.  
The "latest" image is not a released version, but is built from the contents of the master branch.

## Contributing

[CONTRIBUTING](https://github.com/sumeshi/mft2es/blob/master/CONTRIBUTING.md)

The source code for mft2es is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/mft2es).
Please report issues and feature requests. :sushi: :sushi: :sushi:

## License

mft2es is released under the [MIT](https://github.com/sumeshi/mft2es/blob/master/LICENSE) License.

Powered by [pymft-rs](https://github.com/omerbenamram/pymft-rs).
