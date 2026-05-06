package risk.authentication.user.verify.core.policy_0147

# Auto-generated policy 147
# Package: risk.authentication.user.verify.core

# Metadata
metadata := {
    "policy_id": "0147",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0147_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0147_allowed if {
    input.user.active
    input.resource.public
}
policy_0147_allowed if {
    data.policies.risk.enabled
}
policy_0147_approved if {
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
