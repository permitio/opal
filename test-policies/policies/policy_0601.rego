package compliance.validation.action.allow.policy_0601

# Auto-generated policy 601
# Package: compliance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0601",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0601 {
    input.user.role == "admin"
}
default allowed_0601 = false

# Utility function for user info
