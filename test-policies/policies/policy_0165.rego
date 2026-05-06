package compliance.monitoring.user.validate.policy_0165

# Auto-generated policy 165
# Package: compliance.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0165",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0165_allowed if {
    input.user.role == "admin"
}
policy_0165_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0165_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
