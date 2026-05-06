package risk.validation.user.validate.core.policy_0400

# Auto-generated policy 400
# Package: risk.validation.user.validate.core

# Metadata
metadata := {
    "policy_id": "0400",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0400 = false
denied_0400 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
