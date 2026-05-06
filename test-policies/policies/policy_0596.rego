package governance.enforcement.action.deny.policy_0596

# Auto-generated policy 596
# Package: governance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0596",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0596_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0596_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0596_allowed if {
    input.user.role == "admin"
}
default policy_0596_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
