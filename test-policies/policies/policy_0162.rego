package governance.validation.policy.deny.logic.policy_0162

# Auto-generated policy 162
# Package: governance.validation.policy.deny.logic

# Metadata
metadata := {
    "policy_id": "0162",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0162_allowed if {
    data.policies.governance.enabled
}
policy_0162_allowed if {
    input.user.role == "admin"
}
policy_0162_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0162_denied if {
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
