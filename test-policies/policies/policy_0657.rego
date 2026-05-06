package audit.validation.context.allow.data.policy_0657

# Auto-generated policy 657
# Package: audit.validation.context.allow.data

# Metadata
metadata := {
    "policy_id": "0657",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0657 = false
denied_0657 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
