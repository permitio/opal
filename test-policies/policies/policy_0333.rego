package access.enforcement.policy.verify.core.policy_0333

# Auto-generated policy 333
# Package: access.enforcement.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0333",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0333 {
    input.user.active
    input.resource.public
}
denied_0333 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0333 {
    input.user.role == "admin"
}
default allowed_0333 = false

# Utility function for user info
