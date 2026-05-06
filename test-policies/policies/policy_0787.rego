package governance.enforcement.policy.check.helpers.policy_0787

# Auto-generated policy 787
# Package: governance.enforcement.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0787",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0787_allowed if {
    data.policies.governance.enabled
}
default policy_0787_allowed = false
policy_0787_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
