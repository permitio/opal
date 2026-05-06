package governance.enforcement.action.validate.policy_0972

# Auto-generated policy 972
# Package: governance.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0972",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0972 {
    input.user.role == "admin"
}
default allowed_0972 = false
allowed_0972 {
    data.policies.governance.enabled
}
allowed_0972 {
    input.user.active
    input.resource.public
}

# Utility function for user info
