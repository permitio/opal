package compliance.validation.action.verify.data.policy_0216

# Auto-generated policy 216
# Package: compliance.validation.action.verify.data

# Metadata
metadata := {
    "policy_id": "0216",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0216 {
    input.user.active
    input.resource.public
}
allowed_0216 {
    data.policies.compliance.enabled
}
allowed_0216 {
    input.user.role == "admin"
}

# Utility function for user info
