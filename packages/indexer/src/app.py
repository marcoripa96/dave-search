from elasticsearch import Elasticsearch
import uvicorn
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends
import chromadb
from chromadb import errors
from chromadb.config import Settings
import uuid
from sentence_transformers import SentenceTransformer
from functools import lru_cache
from settings import AppSettings
from retriever import DocumentRetriever
from utils import get_facets_annotations, get_facets_metadata, get_hits


@lru_cache()
def get_settings():
    return AppSettings()


# Setup FastAPI:
app = FastAPI()

# I need open CORS for my setup, you may not!!
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/chroma/collection/{collection_name}")
def get_collection(collection_name):
    try:
        return chroma_client.get_collection(name=collection_name)
    except Exception:
        raise HTTPException(status_code=404049, detail="Collection not found")


class CreateCollectionRequest(BaseModel):
    name: str


@app.post("/chroma/collection")
def create_collection(req: CreateCollectionRequest):
    # try:
    collection = chroma_client.get_or_create_collection(name=req.name)
    count = collection.count()

    return {**collection.dict(), "n_documents": count}
    # except Exception:
    #     raise HTTPException(status_code=409, detail="Collection already exists")


@app.get("/chroma/collection/{collection_name}/count")
def count_collection_docs(collection_name):
    try:
        collection = chroma_client.get_collection(collection_name)
        count = collection.count()

        return {"total_docs": count}

    except Exception:
        raise HTTPException(
            status_code=500, detail="Something went wrong when counting documents"
        )


@app.delete("/chroma/collection/{collection_name}")
def delete_collection(collection_name):
    try:
        chroma_client.delete_collection(name=collection_name)
        return {"count": 1}
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Collection not found")


class IndexDocumentRequest(BaseModel):
    embeddings: List[List[float]]
    documents: List[str]
    metadatas: List[dict] = []


@app.post("/chroma/collection/{collection_name}/doc")
def index_chroma_document(req: IndexDocumentRequest, collection_name):
    try:
        collection = chroma_client.get_collection(collection_name)
        chunks_ids = [str(uuid.uuid4()) for _ in req.embeddings]

        collection.add(
            documents=req.documents,
            embeddings=req.embeddings,
            metadatas=req.metadatas,
            ids=chunks_ids,
        )

        return {"added": len(req.embeddings)}
    except errors.IDAlreadyExistsError:
        raise HTTPException(
            status_code=409, detail="A document with the same id already exists"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=req.embeddings)


@app.delete("/chroma/collection/{collection_name}/doc/{document_id}")
def delete_document(collection_name, document_id):
    try:
        # delete indexed embeddings for the document
        collection = chroma_client.get_collection(collection_name)
        collection.delete(where={"doc_id": document_id})
        return {"count": 1}

    except Exception:
        raise HTTPException(
            status_code=500, detail="Something went wrong when deleting the document"
        )


class QueryCollectionRquest(BaseModel):
    query: str
    k: int = 5
    where: dict = None
    include: List[str] = ["metadatas", "documents", "distances"]


@app.post("/chroma/collection/{collection_name}/query")
async def query_collection(collection_name: str, req: QueryCollectionRquest):
    # try:
    # get most similar chunks
    collection = chroma_client.get_collection(collection_name)

    # create embeddings for the query
    embeddings = model.encode(req.query)

    result = collection.query(
        query_embeddings=embeddings.tolist(),
        n_results=req.k,
        where=req.where,
        include=req.include,
    )

    doc_chunk_ids_map = {}

    for index, metadata in enumerate(result["metadatas"][0]):
        chunk = {
            "id": result["ids"][0][index],
            "distance": result["distances"][0][index],
            "metadata": metadata,
            "text": result["documents"][0][index],
        }

        if metadata["doc_id"] in doc_chunk_ids_map:
            doc_chunk_ids_map[metadata["doc_id"]].append(chunk)
        else:
            doc_chunk_ids_map[metadata["doc_id"]] = [chunk]

    # get full documents from db
    doc_ids = list(doc_chunk_ids_map.keys())

    full_docs = []
    for doc_id in doc_ids:
        d = retriever.retrieve(doc_id)
        # d = requests.get(
        #     "http://"
        #     + settings.host_base_url
        #     + ":"
        #     + settings.docs_port
        #     + "/api/mongo/document/"
        #     + str(doc_id)
        # ).json()
        full_docs.append(d)

    doc_results = []

    for doc in full_docs:
        doc_results.append({"doc": doc, "chunks": doc_chunk_ids_map[doc["id"]]})

    return doc_results


class CreateElasticIndexRequest(BaseModel):
    name: str


@app.post("/elastic/index")
def create_elastic_index(req: CreateElasticIndexRequest):
    if es_client.indices.exists(index=req.name):
        index = es_client.indices.get(index=req.name)
        count = es_client.count(index=req.name)

        return {**index, "n_documents": count}

    # try:
    es_client.indices.create(
        index=req.name,
        mappings={
            "properties": {
                "metadata": {
                    "type": "nested",
                    "properties": {
                        "type": {"type": "keyword"},
                        "value": {"type": "keyword"},
                    },
                },
                "annotations": {
                    "type": "nested",
                    "properties": {
                        "id_ER": {"type": "keyword"},
                        "type": {"type": "keyword"},
                    },
                },
            }
        },
    )

    index = es_client.indices.get(index=req.name)

    return {**index, "n_documents": 0}


@app.delete("/elastic/index/{index_name}")
def delete_elastic_index(index_name):
    try:
        es_client.indices.delete(index=index_name)
        return {"count": 1}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Error while deleting index")


class IndexElasticDocumentRequest(BaseModel):
    doc: dict


@app.post("/elastic/index/{index_name}/doc")
def index_elastic_document(req: IndexElasticDocumentRequest, index_name):
    res = es_client.index(index=index_name, document=req.doc)
    es_client.indices.refresh(index=index_name)
    return res["result"]
    # try:
    #     collection = chroma_client.get_collection(collection_name)
    #     chunks_ids = [str(uuid.uuid4()) for _ in req.embeddings]

    #     collection.add(
    #         documents=req.documents,
    #         embeddings=req.embeddings,
    #         metadatas=req.metadatas,
    #         ids=chunks_ids,
    #     )

    #     return {"added": len(req.embeddings)}
    # except errors.IDAlreadyExistsError:
    #     raise HTTPException(
    #         status_code=409, detail="A document with the same id already exists"
    #     )
    # except Exception as e:
    #     raise HTTPException(status_code=500, detail=req.embeddings)


class QueryElasticIndexRequest(BaseModel):
    text: str
    metadata: list = None
    annotations: list = None
    n_facets: int = 20
    page: int = 1
    documents_per_page: int = 20


@app.post("/elastic/index/{index_name}/query")
async def query_elastic_index(
    index_name: str,
    req: QueryElasticIndexRequest,
):
    from_offset = (req.page - 1) * req.documents_per_page

    # build a query that retrieve conditions based AND conditions between text, annotation facets and metadata facets
    query = {
        "bool": {
            "must": [
                {"match": {"text": req.text}},
            ]
        }
    }

    if req.annotations != None and len(req.annotations) > 0:
        for annotation in req.annotations:
            query["bool"]["must"].append(
                {
                    "nested": {
                        "path": "annotations",
                        "query": {
                            "bool": {
                                "filter": [
                                    {
                                        "term": {
                                            "annotations.id_ER": annotation["value"]
                                        }
                                    },
                                    {"term": {"annotations.type": annotation["type"]}},
                                ]
                            }
                        },
                    }
                },
            )

    if req.metadata != None and len(req.metadata) > 0:
        for metadata in req.metadata:
            query["bool"]["must"].append(
                {
                    "nested": {
                        "path": "metadata",
                        "query": {
                            "bool": {
                                "filter": [
                                    {"term": {"metadata.value": metadata["value"]}},
                                    {"term": {"metadata.type": metadata["type"]}},
                                ]
                            }
                        },
                    }
                },
            )

    search_res = es_client.search(
        index=index_name,
        size=req.documents_per_page,
        from_=from_offset,
        query=query,
        aggs={
            "metadata": {
                "nested": {"path": "metadata"},
                "aggs": {
                    "types": {
                        "terms": {"field": "metadata.type", "size": req.n_facets},
                        "aggs": {
                            "values": {
                                "terms": {
                                    "field": "metadata.value",
                                    "size": req.n_facets,
                                    "order": {"_key": "asc"},
                                }
                            }
                        },
                    }
                },
            },
            "annotations": {
                "nested": {"path": "annotations"},
                "aggs": {
                    "types": {
                        "terms": {"field": "annotations.type", "size": req.n_facets},
                        "aggs": {
                            "mentions": {
                                "terms": {
                                    "field": "annotations.id_ER",
                                    "size": req.n_facets,
                                    "order": {"_key": "asc"},
                                },
                                "aggs": {
                                    "top_hits_per_mention": {
                                        "top_hits": {
                                            "_source": [
                                                "annotations.display_name",
                                            ],
                                            "size": 1,
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
            },
        },
    )

    hits = get_hits(search_res)
    annotations_facets = get_facets_annotations(search_res)
    metadata_facets = get_facets_metadata(search_res)
    total_hits = search_res["hits"]["total"]["value"]
    num_pages = total_hits // req.documents_per_page
    if (
        total_hits % req.documents_per_page > 0
    ):  # if there is a remainder, add one more page
        num_pages += 1

    return {
        "hits": hits,
        "facets": {"annotations": annotations_facets, "metadata": metadata_facets},
        "pagination": {
            "current_page": req.page,
            "total_pages": num_pages,
            "total_hits": total_hits,
        },
    }


if __name__ == "__main__":
    settings = get_settings()

    model = SentenceTransformer(settings.embedding_model, cache_folder="../models/")
    chroma_client = chromadb.Client(
        Settings(
            chroma_api_impl="rest",
            chroma_server_host=settings.host_base_url,
            chroma_server_http_port=settings.chroma_port,
        )
    )
    es_client = Elasticsearch(
        hosts=[{"host": "es", "scheme": "http", "port": int(settings.elastic_port)}],
        request_timeout=60,
    )

    DOCS_BASE_URL = "http://" + settings.host_base_url + ":" + settings.docs_port
    retriever = DocumentRetriever(url=DOCS_BASE_URL + "/api/mongo/document")

    # [start fastapi]:
    _PORT = int(settings.indexer_server_port)
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
