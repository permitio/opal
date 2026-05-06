package audit.authentication.context.allow.policy_0334

# Auto-generated policy 334
# Package: audit.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0334",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0334 = false
denied_0334 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
