package audit.enforcement.context.deny.policy_0104

# Auto-generated policy 104
# Package: audit.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0104",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0104 = false
denied_0104 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
