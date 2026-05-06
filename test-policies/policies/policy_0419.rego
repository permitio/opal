package audit.enforcement.policy.deny.policy_0419

# Auto-generated policy 419
# Package: audit.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0419",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0419_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0419_allowed = false
policy_0419_denied if {
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
