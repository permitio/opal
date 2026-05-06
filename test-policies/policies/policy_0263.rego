package audit.enforcement.resource.deny.policy_0263

# Auto-generated policy 263
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0263",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0263 {
    data.policies.audit.enabled
}
allowed_0263 {
    input.user.active
    input.resource.public
}
default allowed_0263 = false

# Utility function for user info
