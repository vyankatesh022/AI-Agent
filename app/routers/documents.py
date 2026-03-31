"""Document management and RAG retrieval endpoints with strict tenant isolation."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.documents.service import DocumentService
from app.llm.factory import LLMFactory
from app.models import User
from app.rag.pipeline import RAGPipeline
from app.schemas import (
    DocumentListResponse,
    DocumentResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents & RAG"])


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and index a PDF document for RAG",
)
async def upload_document(
    file: Annotated[
        UploadFile,
        File(description="PDF document file to upload and index"),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentResponse:
    """Validate, store, extract, chunk, embed, and index a PDF document.

    Enforces:
    - User ownership: Indexing and storage are scoped strictly to the caller.
    - File validation: Validates size, .pdf extension, magic bytes, and PDF structure.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )

    # Read binary content
    try:
        content = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read uploaded file.",
        ) from exc

    service = DocumentService()
    try:
        document = service.process_and_store_document(
            db=db,
            user_id=current_user.id,
            file_bytes=content,
            original_filename=file.filename,
            content_type=file.content_type,
        )
        return DocumentResponse.model_validate(document)
    except ValueError as exc:
        logger.warning("Document ingestion rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents owned by authenticated user",
)
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentListResponse:
    """Return all document records owned by the calling user."""
    service = DocumentService()
    docs = service.list_user_documents(db=db, user_id=current_user.id)
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document metadata by ID",
)
def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentResponse:
    """Fetch metadata for a single document owned by the calling user."""
    service = DocumentService()
    doc = service.get_user_document(
        db=db, user_id=current_user.id, document_id=document_id
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse.model_validate(doc)


@router.delete(
    "/{document_id}",
    summary="Delete a document and purge it from vector index",
)
def delete_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Purge document from database, disk storage, and FAISS index."""
    service = DocumentService()
    deleted = service.delete_user_document(
        db=db, user_id=current_user.id, document_id=document_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return {
        "detail": "Document successfully deleted",
        "document_id": str(document_id),
    }


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="Perform a direct grounded RAG query over user documents",
)
async def query_documents(
    payload: RAGQueryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RAGQueryResponse:
    """Query user documents with semantic retrieval, LLM synthesis, and citations."""
    target_provider = (payload.provider or settings.LLM_PROVIDER).strip().lower()
    if target_provider not in LLMFactory.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported provider '{payload.provider}'. "
                f"Allowed: {sorted(LLMFactory.SUPPORTED_PROVIDERS)}"
            ),
        )

    if payload.model:
        allowed = LLMFactory.ALLOWED_MODELS.get(target_provider, set())
        if payload.model not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported model '{payload.model}'. Allowed: {sorted(allowed)}"
                ),
            )

    try:
        llm_provider = LLMFactory.create_provider(
            provider_name=target_provider,
            model_name=payload.model,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Language model provider is not properly configured.",
        ) from exc

    pipeline = RAGPipeline()
    result = await pipeline.run(
        user_id=current_user.id,
        query=payload.query,
        llm_provider=llm_provider,
        top_k=payload.top_k,
        db=db,
    )

    return RAGQueryResponse(
        query=payload.query,
        response=result.response,
        citations=[
            c.to_dict() if hasattr(c, "to_dict") else c for c in result.citations
        ],
        sources=[s.to_dict() for s in result.sources],
        retrieved_count=result.retrieved_count,
        retrieval_mode=result.retrieval_mode,
        provider=llm_provider.provider_name,
        model=llm_provider.model_name,
    )
