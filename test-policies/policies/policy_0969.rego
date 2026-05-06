package audit.authorization.user.check.policy_0969

# Auto-generated policy 969
# Package: audit.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0969",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0969 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0969 = false

# Utility function for user info
