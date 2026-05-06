package risk.authentication.resource.verify.data.policy_0031

# Auto-generated policy 31
# Package: risk.authentication.resource.verify.data

# Metadata
metadata := {
    "policy_id": "0031",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0031 {
    data.policies.risk.enabled
}
default allowed_0031 = false
allowed_0031 {
    input.user.active
    input.resource.public
}

# Utility function for user info
