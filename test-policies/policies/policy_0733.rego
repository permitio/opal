package governance.enforcement.user.allow.policy_0733

# Auto-generated policy 733
# Package: governance.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0733",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0733_allowed if {
    data.policies.governance.enabled
}
policy_0733_allowed if {
    input.user.role == "admin"
}
policy_0733_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0733_denied if {
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
