package compliance.monitoring.user.validate.policy_0586

# Auto-generated policy 586
# Package: compliance.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0586",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0586 {
    data.policies.compliance.enabled
}
allowed_0586 {
    input.user.role == "admin"
}

# Utility function for user info
