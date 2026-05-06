package governance.enforcement.policy.check.core.policy_0634

# Auto-generated policy 634
# Package: governance.enforcement.policy.check.core

# Metadata
metadata := {
    "policy_id": "0634",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0634_allowed if {
    input.user.role == "admin"
}
policy_0634_allowed if {
    data.policies.governance.enabled
}
policy_0634_allowed if {
    input.user.active
    input.resource.public
}
policy_0634_denied if {
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
