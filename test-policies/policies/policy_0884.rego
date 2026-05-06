package audit.enforcement.resource.validate.logic.policy_0884

# Auto-generated policy 884
# Package: audit.enforcement.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0884",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0884 {
    data.policies.audit.enabled
}
denied_0884 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
