"""Document management routes."""

import os
import shutil
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field
from loguru import logger

from db import get_supabase
from rag.processor import extract_sections, chunk_sections
from rag.embeddings import EmbeddingClient

router = APIRouter()

UPLOAD_DIR = "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md"}

_embedding_client = EmbeddingClient()


class DocumentMetadataPatch(BaseModel):
    summary: Optional[str] = Field(default=None, max_length=2000)
    keywords: Optional[List[str]] = None


def _normalize_keywords(keywords: Optional[List[str]]) -> List[str]:
    if not keywords:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for k in keywords:
        if not isinstance(k, str):
            continue
        k = k.strip().lower()
        if not k or k in seen:
            continue
        if len(k) > 60:
            k = k[:60]
        seen.add(k)
        out.append(k)
        if len(out) >= 30:
            break
    return out


def _process_document(
    doc_id: str,
    bot_id: str,
    doc_name: str,
    file_path: str,
    summary: Optional[str] = None,
    keywords: Optional[List[str]] = None,
):
    """Background task: extract → chunk → embed → store in MongoDB."""
    sb = get_supabase()

    try:
        logger.info(f"[RAG] Extracting text from {file_path}")
        sections = extract_sections(file_path)
        if not sections or not any(s["text"].strip() for s in sections):
            raise ValueError("El archivo está vacío o no tiene texto extraíble.")

        chunks = chunk_sections(sections)
        logger.info(f"[RAG] {len(chunks)} chunks generados")

        logger.info("[RAG] Generando embeddings...")
        embeddings = _embedding_client.embed_batch([c["content"] for c in chunks])

        from pymongo import MongoClient
        from core.config import settings

        mongo = MongoClient(settings.mongodb_uri)
        col = mongo[settings.mongodb_db_name]["doc_chunks"]
        col.delete_many({"doc_id": doc_id})

        processed_at = datetime.now(timezone.utc).isoformat()
        normalized_keywords = _normalize_keywords(keywords)
        docs_to_insert = [
            {
                "doc_id": doc_id,
                "bot_id": bot_id,
                "chunk_index": i,
                "content": chunk["content"],
                "embedding": embedding,
                "doc_name": doc_name,
                "doc_summary": summary or None,
                "doc_keywords": normalized_keywords,
                "page": chunk.get("page"),
                "processed_at": processed_at,
            }
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        col.insert_many(docs_to_insert)
        mongo.close()
        logger.info(f"[RAG] {len(docs_to_insert)} chunks guardados en MongoDB")

        sb.table("documents").update({"status": "ready"}).eq("id", doc_id).execute()
        logger.info(f"[RAG] Documento {doc_id} listo")

    except Exception as e:
        logger.exception(f"[RAG] Error procesando {doc_id}: {e}")
        sb.table("documents").update({"status": "error"}).eq("id", doc_id).execute()


def _sync_chunk_metadata(doc_id: str, summary: Optional[str], keywords: Optional[List[str]]) -> None:
    """Update doc_summary / doc_keywords on existing chunks without re-embedding."""
    try:
        from pymongo import MongoClient
        from core.config import settings

        update: dict = {}
        if summary is not None:
            update["doc_summary"] = summary or None
        if keywords is not None:
            update["doc_keywords"] = _normalize_keywords(keywords)
        if not update:
            return
        mongo = MongoClient(settings.mongodb_uri)
        mongo[settings.mongodb_db_name]["doc_chunks"].update_many(
            {"doc_id": doc_id}, {"$set": update}
        )
        mongo.close()
    except Exception as e:
        logger.warning(f"Could not sync chunk metadata for {doc_id}: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{bot_id}/documents")
async def list_documents(bot_id: str):
    try:
        result = (
            get_supabase()
            .table("documents")
            .select("*")
            .eq("bot_id", bot_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data
    except Exception as e:
        logger.error(f"Error listing documents for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron cargar los documentos.")


@router.post("/{bot_id}/documents", status_code=201)
async def upload_document(
    bot_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Tipo de archivo no permitido. Usa PDF, TXT, DOCX o MD.",
        )

    # Save metadata to Supabase
    try:
        doc_data = {
            "bot_id": bot_id,
            "name": file.filename,
            "status": "processing",
            "file_size": file.size or 0,
        }
        result = get_supabase().table("documents").insert(doc_data).execute()
        doc = result.data[0]
    except Exception as e:
        logger.error(f"Error saving document metadata: {e}")
        raise HTTPException(status_code=500, detail="No se pudo guardar el documento.")

    # Save file to disk
    bot_dir = os.path.join(UPLOAD_DIR, bot_id)
    os.makedirs(bot_dir, exist_ok=True)
    file_path = os.path.join(bot_dir, f"{doc['id']}{ext}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error writing file: {e}")
        raise HTTPException(status_code=500, detail="Error al guardar el archivo.")

    # Trigger RAG processing in background
    background_tasks.add_task(
        _process_document,
        doc["id"],
        bot_id,
        file.filename,
        file_path,
        doc.get("summary"),
        doc.get("keywords") or [],
    )

    return doc


@router.patch("/{bot_id}/documents/{doc_id}")
async def update_document_metadata(bot_id: str, doc_id: str, body: DocumentMetadataPatch):
    if body.summary is None and body.keywords is None:
        raise HTTPException(status_code=400, detail="Sin campos para actualizar.")
    payload: dict = {}
    if body.summary is not None:
        payload["summary"] = body.summary.strip() or None
    if body.keywords is not None:
        payload["keywords"] = _normalize_keywords(body.keywords)
    try:
        result = (
            get_supabase()
            .table("documents")
            .update(payload)
            .eq("id", doc_id)
            .eq("bot_id", bot_id)
            .execute()
        )
    except Exception as e:
        logger.exception(f"Error updating document metadata {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo actualizar el documento.")
    if not result.data:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    _sync_chunk_metadata(doc_id, payload.get("summary"), payload.get("keywords"))
    return result.data[0]


@router.delete("/{bot_id}/documents/{doc_id}", status_code=204)
async def delete_document(bot_id: str, doc_id: str):
    try:
        # Delete chunks from MongoDB
        try:
            from pymongo import MongoClient
            from core.config import settings
            mongo = MongoClient(settings.mongodb_uri)
            mongo[settings.mongodb_db_name]["doc_chunks"].delete_many({"doc_id": doc_id})
            mongo.close()
        except Exception as e:
            logger.warning(f"Could not delete chunks from MongoDB: {e}")

        get_supabase().table("documents").delete().eq("id", doc_id).eq("bot_id", bot_id).execute()
    except Exception as e:
        logger.error(f"Error deleting document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar el documento.")
