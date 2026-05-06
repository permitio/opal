package compliance.enforcement.action.deny.policy_0713

# Auto-generated policy 713
# Package: compliance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0713",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0713_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0713_denied if {
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
