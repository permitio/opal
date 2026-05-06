package audit.validation.policy.deny.policy_0860

# Auto-generated policy 860
# Package: audit.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0860",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0860 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0860 {
    data.policies.audit.enabled
}
allowed_0860 {
    input.user.active
    input.resource.public
}

# Utility function for user info
