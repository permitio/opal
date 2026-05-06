package risk.validation.policy.allow.utils.policy_0228

# Auto-generated policy 228
# Package: risk.validation.policy.allow.utils

# Metadata
metadata := {
    "policy_id": "0228",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0228 {
    input.user.role == "admin"
}
allowed_0228 {
    data.policies.risk.enabled
}
default allowed_0228 = false

# Utility function for user info
