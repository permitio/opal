package governance.monitoring.user.check.policy_0920

# Auto-generated policy 920
# Package: governance.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0920",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0920_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0920_allowed if {
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
