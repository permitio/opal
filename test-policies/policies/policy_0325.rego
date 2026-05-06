package access.validation.policy.validate.policy_0325

# Auto-generated policy 325
# Package: access.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0325",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0325 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0325 {
    input.user.role == "admin"
}
allowed_0325 {
    data.policies.access.enabled
}

# Utility function for user info
