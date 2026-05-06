package governance.enforcement.resource.allow.logic.policy_0142

# Auto-generated policy 142
# Package: governance.enforcement.resource.allow.logic

# Metadata
metadata := {
    "policy_id": "0142",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0142_allowed if {
    input.user.active
    input.resource.public
}
policy_0142_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0142_denied if {
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
