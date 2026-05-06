package access.authorization.action.verify.policy_0191

# Auto-generated policy 191
# Package: access.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0191",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0191 {
    input.user.role == "admin"
}
allowed_0191 {
    input.user.active
    input.resource.public
}
default allowed_0191 = false
allowed_0191 {
    data.policies.access.enabled
}

# Utility function for user info
