package governance.authorization.policy.verify.core.policy_0071

# Auto-generated policy 71
# Package: governance.authorization.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0071",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0071 {
    input.user.role == "admin"
}
allowed_0071 {
    input.user.active
    input.resource.public
}
default allowed_0071 = false

# Utility function for user info
