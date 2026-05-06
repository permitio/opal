package governance.validation.user.allow.policy_0825

# Auto-generated policy 825
# Package: governance.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0825",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0825 {
    input.user.active
    input.resource.public
}
allowed_0825 {
    data.policies.governance.enabled
}
allowed_0825 {
    input.user.role == "admin"
}
denied_0825 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
