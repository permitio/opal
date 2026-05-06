package governance.enforcement.resource.validate.core.policy_0557

# Auto-generated policy 557
# Package: governance.enforcement.resource.validate.core

# Metadata
metadata := {
    "policy_id": "0557",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0557 {
    input.user.role == "admin"
}
default allowed_0557 = false
allowed_0557 {
    data.policies.governance.enabled
}

# Utility function for user info
