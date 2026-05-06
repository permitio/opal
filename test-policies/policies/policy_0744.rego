package access.monitoring.user.verify.policy_0744

# Auto-generated policy 744
# Package: access.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0744",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0744 = false
allowed_0744 {
    input.user.role == "admin"
}
allowed_0744 {
    input.user.active
    input.resource.public
}
allowed_0744 {
    data.policies.access.enabled
}

# Utility function for user info
