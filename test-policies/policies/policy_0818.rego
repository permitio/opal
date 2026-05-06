package security.enforcement.action.verify.data.policy_0818

# Auto-generated policy 818
# Package: security.enforcement.action.verify.data

# Metadata
metadata := {
    "policy_id": "0818",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0818_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0818_allowed if {
    input.user.role == "admin"
}
default policy_0818_allowed = false
policy_0818_denied if {
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
