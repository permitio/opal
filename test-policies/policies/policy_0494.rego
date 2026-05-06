package governance.monitoring.policy.allow.policy_0494

# Auto-generated policy 494
# Package: governance.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0494",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0494_allowed if {
    input.user.role == "admin"
}
policy_0494_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0494_allowed if {
    input.user.active
    input.resource.public
}
policy_0494_allowed if {
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
