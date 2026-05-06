package compliance.authentication.resource.validate.policy_0223

# Auto-generated policy 223
# Package: compliance.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0223",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0223 {
    data.policies.compliance.enabled
}
denied_0223 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
