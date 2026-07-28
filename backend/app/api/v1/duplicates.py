from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.duplicates import DuplicateCluster, MergeDuplicateRequest
from app.services.duplicate_review import keep_both, list_suspected_clusters, merge_cluster

router = APIRouter(prefix="/review/duplicates", tags=["duplicates"])


@router.get("", response_model=list[DuplicateCluster])
def get_duplicates(db: Session = Depends(get_db)) -> list:
    return list_suspected_clusters(db)


@router.post("/{cluster_id}/merge")
def post_merge(cluster_id: int, body: MergeDuplicateRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return merge_cluster(db, cluster_id, body.keep_transaction_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/{cluster_id}/keep-both")
def post_keep_both(cluster_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return keep_both(db, cluster_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
