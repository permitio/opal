package audit.enforcement.resource.allow.policy_0284

# Auto-generated policy 284
# Package: audit.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0284",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0284 {
    data.policies.audit.enabled
}
allowed_0284 {
    input.user.active
    input.resource.public
}
allowed_0284 {
    input.user.role == "admin"
}
denied_0284 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
