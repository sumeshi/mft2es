# Mft2es
[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)

Import Windows Master File Table($MFT) to ElasticSearch.

mft2es uses Rust library [pymft-rs](https://github.com/omerbenamram/pymft-rs).

## Usage
```bash
$ mft2es /path/to/your/$MFT
```

or

```python
from mft2es.mft2es import mft2es

if __name__ == '__main__':
    filepath = '/path/to/your/$MFT'
    mft2es(filepath)
```

### Options
```
--host: 
    ElasticSearch host address
    (default: localhost)

--port: 
    ElasticSearch port number
    (default: 9200)

--index: 
    Index name
    (default: mft2es)

--type: 
    Document-type name
    (default: mft2es)

--size:
    bulk insert size
    (default: 500)
```

### Examples
```
$ mft2es /path/to/your/$MFT --host=localhost --port=9200 --index=foo --type=bar --size=500
```

```py
if __name__ == '__main__':
    mft2es('/path/to/your/$MFT', host=localhost, port=9200, index='foo', type='bar', size=500)
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
            "vnc_last": 15231,
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
            "vnc_last": 2,
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
```

## Installation
### via pip
```
$ pip install git+https://github.com/sumeshi/mft2es
```

The source code for mft2es is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/mft2es).

Please report issues and feature requests. :sushi: :sushi: :sushi:

## License
mft2es is released under the [MIT](https://github.com/sumeshi/mft2es/blob/master/LICENSE) License.

Powered by [pymft-rs](https://github.com/omerbenamram/pymft-rs).  
