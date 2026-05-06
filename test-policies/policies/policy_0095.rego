package governance.validation.action.check.data.policy_0095

# Auto-generated policy 95
# Package: governance.validation.action.check.data

# Metadata
metadata := {
    "policy_id": "0095",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0095 {
    input.user.role == "admin"
}
allowed_0095 {
    input.user.active
    input.resource.public
}
allowed_0095 {
    data.policies.governance.enabled
}

# Utility function for user info
