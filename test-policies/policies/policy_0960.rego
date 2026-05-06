package security.enforcement.policy.check.policy_0960

# Auto-generated policy 960
# Package: security.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0960",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0960 {
    data.policies.security.enabled
}
denied_0960 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0960 {
    input.user.active
    input.resource.public
}

# Utility function for user info
