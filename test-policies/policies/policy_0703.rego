package access.enforcement.context.check.logic.policy_0703

# Auto-generated policy 703
# Package: access.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0703",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0703 {
    data.policies.access.enabled
}
denied_0703 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
