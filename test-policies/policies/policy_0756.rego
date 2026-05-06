package access.enforcement.resource.check.policy_0756

# Auto-generated policy 756
# Package: access.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0756",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0756_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0756_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0756_allowed if {
    data.policies.access.enabled
}
default policy_0756_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
