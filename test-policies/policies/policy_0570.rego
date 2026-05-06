package access.enforcement.action.check.data.policy_0570

# Auto-generated policy 570
# Package: access.enforcement.action.check.data

# Metadata
metadata := {
    "policy_id": "0570",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0570_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0570_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0570_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
