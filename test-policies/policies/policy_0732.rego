package audit.monitoring.user.allow.policy_0732

# Auto-generated policy 732
# Package: audit.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0732",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0732_allowed if {
    input.user.role == "admin"
}
policy_0732_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0732_allowed if {
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
