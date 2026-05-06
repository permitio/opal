package compliance.validation.action.verify.data.policy_0465

# Auto-generated policy 465
# Package: compliance.validation.action.verify.data

# Metadata
metadata := {
    "policy_id": "0465",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0465 = false
allowed_0465 {
    input.user.role == "admin"
}
allowed_0465 {
    data.policies.compliance.enabled
}
allowed_0465 {
    input.user.active
    input.resource.public
}

# Utility function for user info
