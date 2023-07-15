def get_hits(search_res):
    def convert_hit(hit):
        text = hit["_source"].pop("text")
        rest = hit["_source"]
        return {"_id": hit["_id"], "text": text[:300], **rest}

    return [convert_hit(hit) for hit in search_res["hits"]["hits"]]


def get_facets_annotations(search_res):
    def convert_annotation_bucket(bucket):
        return {
            "key": bucket["key"],
            "n_children": len(bucket["mentions"]["buckets"]),
            "doc_count": bucket["doc_count"],
            "children": bucket["mentions"]["buckets"],
        }

    return [
        convert_annotation_bucket(bucket)
        for bucket in search_res["aggregations"]["annotations"]["types"]["buckets"]
    ]


def get_facets_metadata(search_res):
    def convert_annotation_bucket(bucket):
        # filter empty velues. Some documents may not have some metadata
        children = [x for x in bucket["values"]["buckets"] if x["key"] != ""]

        return {
            "key": bucket["key"],
            "n_children": len(children),
            "doc_count": bucket["doc_count"],
            "children": children,
        }

    return [
        convert_annotation_bucket(bucket)
        for bucket in search_res["aggregations"]["metadata"]["types"]["buckets"]
    ]
