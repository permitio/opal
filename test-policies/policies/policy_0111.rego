package risk.monitoring.resource.check.policy_0111

# Auto-generated policy 111
# Package: risk.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0111",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0111_allowed = false
policy_0111_allowed if {
    input.user.role == "admin"
}
policy_0111_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0111_allowed if {
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
