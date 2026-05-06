package compliance.authorization.resource.allow.policy_0478

# Auto-generated policy 478
# Package: compliance.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0478",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0478 = false
allowed_0478 {
    input.user.role == "admin"
}
allowed_0478 {
    data.policies.compliance.enabled
}

# Utility function for user info
