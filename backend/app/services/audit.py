from ..models import AuditLog

def log(db, actor, action, entity, entity_id=None, detail=""):
    """Record the server-authenticated actor; never accept identity from a request body."""
    db.add(AuditLog(
        actor_role=actor.role,
        actor_user_id=actor.id,
        actor_username=actor.username,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail[:500],
    ))


def log_system(db, action, entity, entity_id=None, detail=""):
    """Record a non-user operation such as a scheduled maintenance command."""
    db.add(AuditLog(
        actor_role="system",
        actor_user_id=None,
        actor_username="system",
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail[:500],
    ))
