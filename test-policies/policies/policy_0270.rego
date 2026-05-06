package governance.authentication.policy.allow.policy_0270

# Auto-generated policy 270
# Package: governance.authentication.policy.allow

# Metadata
metadata := {
    "policy_id": "0270",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0270_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0270_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0270_allowed if {
    data.policies.governance.enabled
}
policy_0270_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
