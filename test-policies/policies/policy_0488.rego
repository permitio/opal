package governance.validation.context.deny.helpers.policy_0488

# Auto-generated policy 488
# Package: governance.validation.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0488",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0488 {
    input.user.role == "admin"
}
allowed_0488 {
    data.policies.governance.enabled
}

# Utility function for user info
