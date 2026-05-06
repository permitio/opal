package governance.authentication.resource.deny.core.policy_0079

# Auto-generated policy 79
# Package: governance.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0079",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0079 {
    data.policies.governance.enabled
}
allowed_0079 {
    input.user.role == "admin"
}

# Utility function for user info
