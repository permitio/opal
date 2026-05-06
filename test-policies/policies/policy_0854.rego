package compliance.validation.user.validate.policy_0854

# Auto-generated policy 854
# Package: compliance.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0854",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0854 {
    input.user.active
    input.resource.public
}
allowed_0854 {
    data.policies.compliance.enabled
}
denied_0854 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
