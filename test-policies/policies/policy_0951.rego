package compliance.monitoring.context.allow.helpers.policy_0951

# Auto-generated policy 951
# Package: compliance.monitoring.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0951",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0951_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0951_allowed = false
policy_0951_denied if {
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
