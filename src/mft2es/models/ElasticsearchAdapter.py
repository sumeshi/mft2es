"""MFT-specific Elasticsearch source conversions; input and IDs stay intact."""

from copy import deepcopy


class ElasticsearchAdapter:
    def __init__(self, client):
        self.es = client

    def prepare_records(self, records, index_name):
        return records

    def prepare_source(self, record):
        data = record.get("attributes", {}).get("DATA", {}).get("data")
        attributes = record.get("attributes", {}).values()
        if "windows" in record:
            attributes = [record["windows"]["mft"]["attribute"]]
        if not isinstance(data, str) and not any(
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
