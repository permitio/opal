package audit.validation.policy.deny.policy_0530

# Auto-generated policy 530
# Package: audit.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0530",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0530 {
    data.policies.audit.enabled
}
allowed_0530 {
    input.user.active
    input.resource.public
}
denied_0530 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
