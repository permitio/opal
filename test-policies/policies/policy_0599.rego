package compliance.authorization.user.validate.policy_0599

# Auto-generated policy 599
# Package: compliance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0599",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0599 {
    input.user.role == "admin"
}
allowed_0599 {
    input.user.active
    input.resource.public
}
allowed_0599 {
    data.policies.compliance.enabled
}

# Utility function for user info
