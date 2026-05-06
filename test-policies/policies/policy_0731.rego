package access.authentication.resource.deny.core.policy_0731

# Auto-generated policy 731
# Package: access.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0731",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0731 {
    data.policies.access.enabled
}
allowed_0731 {
    input.user.role == "admin"
}
allowed_0731 {
    input.user.active
    input.resource.public
}

# Utility function for user info
