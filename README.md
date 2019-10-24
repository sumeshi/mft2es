# Mft2es(Alpha)

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
