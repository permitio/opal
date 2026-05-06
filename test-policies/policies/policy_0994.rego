package governance.validation.policy.verify.policy_0994

# Auto-generated policy 994
# Package: governance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0994",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0994 {
    input.user.role == "admin"
}
allowed_0994 {
    data.policies.governance.enabled
}
default allowed_0994 = false
allowed_0994 {
    input.user.active
    input.resource.public
}

# Utility function for user info
