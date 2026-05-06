package security.enforcement.context.check.data.policy_0116

# Auto-generated policy 116
# Package: security.enforcement.context.check.data

# Metadata
metadata := {
    "policy_id": "0116",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0116 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0116 = false

# Utility function for user info
