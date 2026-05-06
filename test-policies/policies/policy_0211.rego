package audit.enforcement.user.allow.policy_0211

# Auto-generated policy 211
# Package: audit.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0211",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0211 {
    input.user.role == "admin"
}
default allowed_0211 = false
allowed_0211 {
    data.policies.audit.enabled
}
denied_0211 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
