from pydantic import BaseSettings
import os


class AppSettings(BaseSettings):
    host_base_url: str = os.getenv("HOST_BASE_URL", "localhost")
    indexer_server_port: str = os.getenv("INDEXER_SERVER_PORT", "7863")
    docs_port: str = os.getenv("DOCS_PORT", "50080")
    chroma_port: str = os.getenv("CHROMA_PORT", "8000")
    elastic_port: str = os.getenv("ELASTIC_PORT", "9200")
    embedding_model: str = os.getenv(
        "SENTENCE_TRANSFORMER_EMBEDDING_MODEL", "efederici/sentence-IT5-base"
    )
    chunk_size: int = 200
    chunk_overlap: int = 20
    index_collection_name: str = "test"
