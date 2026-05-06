package security.monitoring.context.deny.policy_0282

# Auto-generated policy 282
# Package: security.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0282",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0282_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0282_allowed if {
    input.user.role == "admin"
}
policy_0282_denied if {
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
