package governance.authorization.resource.check.policy_0714

# Auto-generated policy 714
# Package: governance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0714",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0714_allowed if {
    data.policies.governance.enabled
}
policy_0714_allowed if {
    input.user.role == "admin"
}
default policy_0714_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
