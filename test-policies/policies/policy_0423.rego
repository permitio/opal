package governance.enforcement.context.allow.policy_0423

# Auto-generated policy 423
# Package: governance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0423",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0423 {
    input.user.role == "admin"
}
allowed_0423 {
    data.policies.governance.enabled
}
denied_0423 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
