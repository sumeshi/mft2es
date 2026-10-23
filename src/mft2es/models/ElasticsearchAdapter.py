"""MFT-specific Elasticsearch source conversions; input and IDs stay intact."""

from copy import deepcopy


class ElasticsearchAdapter:
    def __init__(self, client):
        self.es = client

    def prepare_records(self, records, index_name):
        return records

    def prepare_source(self, record):
        source = deepcopy(record)
        data = record.get("attributes", {}).get("DATA", {}).get("data")
        if isinstance(data, str):
            # Resident and non-resident DATA must share one object mapping.
            source["attributes"]["DATA"]["data"] = {"resident_data": data}
        # Unsigned VCNs, including sentinels, can exceed signed long range.
        attributes = source.get("attributes", {}).values()
        if "windows" in source:
            attributes = [source["windows"]["mft"]["attribute"]]
        for attribute in attributes:
            header = attribute.get("header", {}).get("residential_header", {})
            for field in ("vnc_first", "vnc_last"):
                if isinstance(header.get(field), int):
                    header[field] = hex(header[field])
        return source
