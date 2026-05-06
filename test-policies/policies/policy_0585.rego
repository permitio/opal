package audit.enforcement.policy.check.core.policy_0585

# Auto-generated policy 585
# Package: audit.enforcement.policy.check.core

# Metadata
metadata := {
    "policy_id": "0585",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0585 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0585 = false
allowed_0585 {
    input.user.active
    input.resource.public
}
allowed_0585 {
    input.user.role == "admin"
}

# Utility function for user info
