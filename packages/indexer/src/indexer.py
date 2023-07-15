from sentence_transformers import SentenceTransformer
from chunker import DocumentChunker
from actions import (
    index_chroma_document,
    create_chroma_collection,
    index_elastic_document,
    create_elastic_index,
)


class ChromaIndexer:
    def __init__(self, embedding_model: str, chunk_size: int, chunk_overlap: int):
        self.embedding_model = SentenceTransformer(embedding_model)
        self.chunker = DocumentChunker(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    def __embed(self, text: str):
        chunks = self.chunker.chunk(text)

        embeddings = self.embedding_model.encode(chunks)

        return chunks, embeddings.tolist()

    def create_index(self, name: str):
        return create_chroma_collection(name)

    def index(self, collection: str, doc: dict, metadata):
        chunks, embeddings = self.__embed(doc["text"])

        metadatas = [metadata for _ in chunks]

        return index_chroma_document(
            collection,
            {
                "documents": chunks,
                "embeddings": embeddings,
                "metadatas": metadatas,
            },
        )


class ElasticsearchIndexer:
    def create_index(self, name: str):
        return create_elastic_index(name)

    def index(self, index: str, doc: dict):
        annotations = [
            {
                "id": ann["id"],
                "start": ann["start"],
                "end": ann["end"],
                "type": ann["type"],
                "mention": ann["features"]["mention"],
            }
            for ann in doc["annotation_sets"]["entities_merged"]["annotations"]
        ]

        metadata = [
            # for now let's make them static
            {"type": "anno sentenza", "value": doc["features"].get("annosentenza", "")},
            {"type": "anno ruolo", "value": doc["features"].get("annoruolo", "")},
        ]

        elastic_doc = {
            "mongo_id": doc["id"],
            "name": doc["name"],
            "text": doc["text"],
            "metadata": metadata,
            "annotations": annotations,
        }

        return index_elastic_document(index, elastic_doc)
