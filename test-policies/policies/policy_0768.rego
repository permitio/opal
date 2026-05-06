package governance.validation.context.validate.utils.policy_0768

# Auto-generated policy 768
# Package: governance.validation.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0768",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0768 = false
allowed_0768 {
    data.policies.governance.enabled
}
allowed_0768 {
    input.user.role == "admin"
}

# Utility function for user info
