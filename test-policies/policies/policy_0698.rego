package risk.enforcement.action.verify.policy_0698

# Auto-generated policy 698
# Package: risk.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0698",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0698_allowed if {
    data.policies.risk.enabled
}
policy_0698_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0698_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0698_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
