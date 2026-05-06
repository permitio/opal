package audit.validation.policy.deny.core.policy_0171

# Auto-generated policy 171
# Package: audit.validation.policy.deny.core

# Metadata
metadata := {
    "policy_id": "0171",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0171 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0171 {
    input.user.active
    input.resource.public
}
allowed_0171 {
    data.policies.audit.enabled
}

# Utility function for user info
