package access.authentication.policy.check.policy_0547

# Auto-generated policy 547
# Package: access.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0547",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0547_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0547_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0547_allowed if {
    data.policies.access.enabled
}
policy_0547_allowed if {
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
