package governance.authentication.resource.allow.policy_0370

# Auto-generated policy 370
# Package: governance.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0370",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0370 = false
allowed_0370 {
    input.user.role == "admin"
}
allowed_0370 {
    data.policies.governance.enabled
}

# Utility function for user info
