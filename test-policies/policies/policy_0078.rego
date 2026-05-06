package security.monitoring.context.validate.data.policy_0078

# Auto-generated policy 78
# Package: security.monitoring.context.validate.data

# Metadata
metadata := {
    "policy_id": "0078",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0078_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0078_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0078_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
