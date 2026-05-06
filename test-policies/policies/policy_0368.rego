package security.validation.action.verify.policy_0368

# Auto-generated policy 368
# Package: security.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0368",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0368 = false
allowed_0368 {
    input.user.role == "admin"
}

# Utility function for user info
