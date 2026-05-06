package governance.authorization.action.verify.helpers.policy_0477

# Auto-generated policy 477
# Package: governance.authorization.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0477",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0477_allowed = false
policy_0477_allowed if {
    input.user.role == "admin"
}
policy_0477_allowed if {
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
