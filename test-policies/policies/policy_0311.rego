package compliance.enforcement.context.validate.policy_0311

# Auto-generated policy 311
# Package: compliance.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0311",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0311_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0311_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
