package risk.enforcement.policy.deny.policy_0087

# Auto-generated policy 87
# Package: risk.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0087",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0087 {
    data.policies.risk.enabled
}
allowed_0087 {
    input.user.role == "admin"
}
allowed_0087 {
    input.user.active
    input.resource.public
}

# Utility function for user info
