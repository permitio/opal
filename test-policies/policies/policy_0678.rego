package governance.authentication.policy.allow.policy_0678

# Auto-generated policy 678
# Package: governance.authentication.policy.allow

# Metadata
metadata := {
    "policy_id": "0678",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0678_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0678_allowed = false
policy_0678_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
