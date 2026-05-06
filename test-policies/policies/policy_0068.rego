package risk.enforcement.user.allow.policy_0068

# Auto-generated policy 68
# Package: risk.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0068",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0068_allowed if {
    input.user.active
    input.resource.public
}
policy_0068_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0068_allowed = false
policy_0068_denied if {
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
