"""MFT-specific Elasticsearch source conversions; input and IDs stay intact."""

from copy import deepcopy
from itertools import chain


class ElasticsearchAdapter:
    def __init__(self, client):
        self.es = client

    def prepare_records(self, records, index_name):
        return records

    def prepare_source(self, record):
        data_attributes = record.get("attributes", {}).get("DATA", [])
        attributes = chain.from_iterable(record.get("attributes", {}).values())
        if "windows" in record:
            attributes = [record["windows"]["mft"]["attribute"]]
        if not any(
            isinstance(attribute.get("data"), str) for attribute in data_attributes
        ) and not any(
            isinstance(
                attribute.get("header", {}).get("residential_header", {}).get(field),
                int,
            )
            for attribute in attributes
            for field in ("vnc_first", "vnc_last")
        ):
            # Bulk serialization does not mutate its source. Most Timeline
            # events need no conversion, so avoid copying their whole tree.
            return record

        source = deepcopy(record)
        for attribute in source.get("attributes", {}).get("DATA", []):
            if isinstance(attribute.get("data"), str):
                # Resident and non-resident DATA must share one object mapping.
                attribute["data"] = {"resident_data": attribute["data"]}
        # Unsigned VCNs, including sentinels, can exceed signed long range.
        attributes = chain.from_iterable(source.get("attributes", {}).values())
        if "windows" in source:
            attributes = [source["windows"]["mft"]["attribute"]]
        for attribute in attributes:
            header = attribute.get("header", {}).get("residential_header", {})
            for field in ("vnc_first", "vnc_last"):
                if isinstance(header.get(field), int):
                    header[field] = hex(header[field])
        return source
