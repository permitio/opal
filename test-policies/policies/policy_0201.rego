package risk.authentication.user.allow.policy_0201

# Auto-generated policy 201
# Package: risk.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0201",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0201 = false
allowed_0201 {
    input.user.role == "admin"
}
allowed_0201 {
    data.policies.risk.enabled
}
allowed_0201 {
    input.user.active
    input.resource.public
}

# Utility function for user info
