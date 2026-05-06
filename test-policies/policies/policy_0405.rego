package security.validation.resource.deny.helpers.policy_0405

# Auto-generated policy 405
# Package: security.validation.resource.deny.helpers

# Metadata
metadata := {
    "policy_id": "0405",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0405 {
    input.user.role == "admin"
}
default allowed_0405 = false

# Utility function for user info
