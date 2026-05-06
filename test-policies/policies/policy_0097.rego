package compliance.enforcement.user.deny.policy_0097

# Auto-generated policy 97
# Package: compliance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0097",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0097 {
    data.policies.compliance.enabled
}
allowed_0097 {
    input.user.role == "admin"
}

# Utility function for user info
