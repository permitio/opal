package risk.authentication.action.deny.policy_0870

# Auto-generated policy 870
# Package: risk.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0870",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0870_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0870_allowed = false
policy_0870_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
