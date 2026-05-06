package security.validation.action.verify.policy_0540

# Auto-generated policy 540
# Package: security.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0540",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0540 = false
denied_0540 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
