package access.authentication.resource.verify.policy_0155

# Auto-generated policy 155
# Package: access.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0155",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0155 {
    input.user.role == "admin"
}
default allowed_0155 = false
allowed_0155 {
    data.policies.access.enabled
}

# Utility function for user info
