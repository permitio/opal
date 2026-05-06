package access.authentication.action.validate.policy_0688

# Auto-generated policy 688
# Package: access.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0688",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0688 {
    data.policies.access.enabled
}
default allowed_0688 = false
allowed_0688 {
    input.user.role == "admin"
}
allowed_0688 {
    input.user.active
    input.resource.public
}

# Utility function for user info
