package risk.monitoring.context.deny.core.policy_0345

# Auto-generated policy 345
# Package: risk.monitoring.context.deny.core

# Metadata
metadata := {
    "policy_id": "0345",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0345_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0345_allowed if {
    data.policies.risk.enabled
}
default policy_0345_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
