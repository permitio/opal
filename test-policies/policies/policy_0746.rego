package audit.validation.resource.deny.policy_0746

# Auto-generated policy 746
# Package: audit.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0746",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0746 {
    data.policies.audit.enabled
}
denied_0746 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
