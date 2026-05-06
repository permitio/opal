package security.authorization.policy.deny.policy_0759

# Auto-generated policy 759
# Package: security.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0759",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0759 {
    input.user.active
    input.resource.public
}
allowed_0759 {
    data.policies.security.enabled
}
denied_0759 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0759 = false

# Utility function for user info
