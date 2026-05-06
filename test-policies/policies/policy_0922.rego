package compliance.authorization.resource.validate.logic.policy_0922

# Auto-generated policy 922
# Package: compliance.authorization.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0922",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0922 {
    data.policies.compliance.enabled
}
default allowed_0922 = false
allowed_0922 {
    input.user.role == "admin"
}

# Utility function for user info
