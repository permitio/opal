package access.authentication.context.verify.logic.policy_0549

# Auto-generated policy 549
# Package: access.authentication.context.verify.logic

# Metadata
metadata := {
    "policy_id": "0549",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0549_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0549_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0549_allowed if {
    input.user.role == "admin"
}
policy_0549_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
