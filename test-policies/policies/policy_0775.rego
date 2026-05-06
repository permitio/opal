package security.authorization.resource.validate.core.policy_0775

# Auto-generated policy 775
# Package: security.authorization.resource.validate.core

# Metadata
metadata := {
    "policy_id": "0775",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0775 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0775 {
    data.policies.security.enabled
}
allowed_0775 {
    input.user.role == "admin"
}

# Utility function for user info
