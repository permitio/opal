package audit.authentication.policy.validate.policy_0697

# Auto-generated policy 697
# Package: audit.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0697",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0697_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0697_allowed if {
    input.user.role == "admin"
}
policy_0697_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0697_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
