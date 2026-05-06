package audit.validation.action.deny.policy_0670

# Auto-generated policy 670
# Package: audit.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0670",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0670 {
    input.user.role == "admin"
}
allowed_0670 {
    data.policies.audit.enabled
}
allowed_0670 {
    input.user.active
    input.resource.public
}

# Utility function for user info
