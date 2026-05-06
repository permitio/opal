package risk.enforcement.policy.check.policy_0108

# Auto-generated policy 108
# Package: risk.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0108",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0108 = false
allowed_0108 {
    input.user.active
    input.resource.public
}
allowed_0108 {
    input.user.role == "admin"
}

# Utility function for user info
