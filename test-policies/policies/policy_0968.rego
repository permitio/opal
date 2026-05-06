package access.enforcement.user.verify.policy_0968

# Auto-generated policy 968
# Package: access.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0968",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0968_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0968_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0968_allowed if {
    data.policies.access.enabled
}
default policy_0968_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
