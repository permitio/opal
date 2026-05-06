package access.enforcement.user.check.data.policy_0328

# Auto-generated policy 328
# Package: access.enforcement.user.check.data

# Metadata
metadata := {
    "policy_id": "0328",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0328 {
    input.user.role == "admin"
}
denied_0328 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
