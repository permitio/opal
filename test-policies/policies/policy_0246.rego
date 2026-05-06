package audit.authentication.user.allow.data.policy_0246

# Auto-generated policy 246
# Package: audit.authentication.user.allow.data

# Metadata
metadata := {
    "policy_id": "0246",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0246 {
    data.policies.audit.enabled
}
default allowed_0246 = false
denied_0246 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
