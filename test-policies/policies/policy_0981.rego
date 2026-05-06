package compliance.monitoring.user.deny.policy_0981

# Auto-generated policy 981
# Package: compliance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0981",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0981_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0981_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0981_allowed if {
    input.user.role == "admin"
}
policy_0981_allowed if {
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
